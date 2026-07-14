"""
전처리 에이전트: QuestionExtractorAgent
========================================
역할: builder 노드가 GitHub 코드를 수집한 직후 단 한 번 실행됩니다.
     소스코드 + 이력서 + 기업 인재상 + 분야별 최신 트렌드를 종합 분석하여 
     면접 질문 풀(question_pool)을 사전에 생성합니다.

실시간 인터랙션 에이전트들은 이 풀에서 질문을 꺼내어 사용하며,
턴마다 LLM을 호출해 질문을 새로 만들지 않아도 됩니다.
"""

from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from app.schemas import InterviewState
from app.core.llm import get_llm
from app.service.vector_service import get_vector_service

# 기업 프로필 및 트렌드 데이터 임포트
try:
    from app.data.company_profiles import COMPANY_PROFILES, FIELD_TRENDS
except ImportError:
    COMPANY_PROFILES = {}
    FIELD_TRENDS = {}


# ──────────────────────────────────────────────────────────────────────────────
# 0. 구조화 출력 스키마
# ──────────────────────────────────────────────────────────────────────────────

class QuestionItem(BaseModel):
    question: str = Field(description="지원자에게 던질 기술 면접 질문 (한국어 존댓말)")
    source: str = Field(
        description=(
            "질문 출처 구분: "
            "'code' (제출된 GitHub 소스코드 기반), "
            "'resume' (이력서에 기재된 다른 프로젝트/경험 기반)"
        ),
        default="code"
    )
    file_path: Optional[str] = Field(None, description="질문과 연관된 소스코드 파일 경로 (source='code'일 때만 지정)")
    start_line: Optional[int] = Field(None, description="연관 코드 시작 줄 번호 (1-indexed)")
    end_line: Optional[int] = Field(None, description="연관 코드 끝 줄 번호 (1-indexed)")
    difficulty: str = Field(
        description="질문 난이도: 'easy' | 'medium' | 'hard'",
        default="medium"
    )


class QuestionPool(BaseModel):
    questions: list[QuestionItem] = Field(
        description="사전 생성된 기술 면접 질문 목록 (난이도 순 정렬, 최소 5개)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. 코드 컨텍스트 빌더 (줄번호 포함)
# ──────────────────────────────────────────────────────────────────────────────

def _build_code_context(chunks: list, rag_chunks: list) -> str:
    """state 청크 + RAG 검색 결과를 줄번호 포함 텍스트로 조합합니다."""
    context = ""

    # README.md를 항상 첫 번째로 포함 (기술 스택 정보 포함)
    readme_added = False
    
    for chunk in chunks:
        file_path = chunk.get("file_path", "unknown")
        code_text = chunk.get("content") or chunk.get("code", "")
        
        # README.md 특별 처리
        if file_path.endswith("README.md") or "README" in file_path.upper():
            context = f"--- File: {file_path} ---\n" + context
            for idx, line in enumerate(code_text.split("\n"), 1):
                context = f"{idx}: {line}\n" + context
            context = context + "\n"
            readme_added = True
        else:
            context += f"--- File: {file_path} ---\n"
            for idx, line in enumerate(code_text.split("\n"), 1):
                context += f"{idx}: {line}\n"
            context += "\n"

    # README.md가 청크에 없으면 직접 읽어서 추가
    if not readme_added:
        try:
            with open("README.md", "r", encoding="utf-8") as f:
                readme_content = f.read()
                context = f"--- File: README.md ---\n" + context
                for idx, line in enumerate(readme_content.split("\n"), 1):
                    context = f"{idx}: {line}\n" + context
                context = context + "\n"
        except Exception:
            pass  # README.md 읽기 실패 시 무시

    for i, rc in enumerate(rag_chunks, start=1):
        file_path = rc.get("file_path", "unknown")
        code_text = rc.get("content", "")
        context += f"--- [RAG #{i}] File: {file_path} ---\n"
        for idx, line in enumerate(code_text.split("\n"), 1):
            context += f"{idx}: {line}\n"
        context += "\n"

    return context.strip() or "분석 가능한 소스코드 파일이 없습니다."


# ──────────────────────────────────────────────────────────────────────────────
# 2. 전처리 노드 메인 함수
# ──────────────────────────────────────────────────────────────────────────────

def extract_question_pool(state: InterviewState) -> dict:
    """
    [전처리 에이전트] 코드 분석 → 질문 풀 사전 생성

    builder 실행 후 1회만 호출됩니다.
    - 소스코드 + 이력서 + 기업 인재상 + 분야별 최신 트렌드를 LLM에 한 번에 던져 5~7개의 질문을 미리 만들어둡니다.
    - 이후 실시간 인터랙션 에이전트(evaluator 흐름)는 이 풀에서 순서대로 꺼내씁니다.
    """
    llm = get_llm(temperature=0.8)
    structured_llm = llm.with_structured_output(QuestionPool)

    tech_stack = ", ".join(state.get("tech_stack", []))
    chunks = state.get("extracted_chunks", [])
    repo_url = state.get("repo_url", "")
    
    # 🏢 기업 및 분야 정보 추출
    target_company = state.get("target_company", "")
    target_field = state.get("target_field", "")
    company_values = state.get("company_values", "")

    # ── 이력서 포맷팅 ──────────────────────────────────────────────────────────
    resume_text = state.get("resume_text", "")
    if resume_text:
        safe_resume = resume_text.replace("{", "{{").replace("}", "}}")
        resume_context = (
            f"--- [지원자 이력서 (Resume)] ---\n{safe_resume}\n"
            "--------------------------------"
        )
    else:
        resume_context = "제공된 이력서가 없습니다. 소스코드 분석 중심의 질문을 생성하세요."

    # ── 🏢 기업 인재상 및 면접 스타일 컨텍스트 구성 ────────────────────────────
    company_context = ""
    if target_company:
        if company_values.startswith("auto:"):
            # 사전 정의된 기업의 경우
            company_name = company_values.replace("auto:", "")
            if company_name in COMPANY_PROFILES:
                profile = COMPANY_PROFILES[company_name]
                company_context = f"""
--- [목표 기업: {profile['name']}] ---
인재상: {', '.join(profile['values'])}
기업 문화: {profile['culture']}
면접 스타일: {profile['interview_style']}
기술 포커스: {', '.join(profile['tech_focus'])}
최근 트렌드: {', '.join(profile['recent_trends'])}
--------------------------------"""
        else:
            # 직접 입력된 기업 정보
            company_context = f"""
--- [목표 기업: {target_company}] ---
인재상/핵심가치: {company_values}
--------------------------------"""
    
    # ── 🎯 분야별 최신 IT 트렌드 컨텍스트 구성 ─────────────────────────────────
    field_context = ""
    if target_field and target_field in FIELD_TRENDS:
        trends = FIELD_TRENDS[target_field]
        field_context = f"""
--- [목표 분야: {target_field} - 2024년 최신 트렌드] ---
최신 트렌드: {', '.join(trends['trends'])}
핵심 기술: {', '.join(trends['skills'])}
--------------------------------"""
    elif target_field:
        field_context = f"""
--- [목표 분야: {target_field}] ---
해당 분야의 최신 기술 동향과 실무 경험을 중심으로 질문을 구성하세요.
--------------------------------"""

    # ── RAG 보강 검색 ──────────────────────────────────────────────────────────
    rag_query = tech_stack or "코드 구조 및 설계"
    try:
        rag_chunks = get_vector_service().search(
            query=rag_query,
            filters={"repo_url": repo_url} if repo_url else None,
            n_results=3,
        )
    except Exception:
        rag_chunks = []

    code_context = _build_code_context(chunks, rag_chunks)

    # ── 프롬프트 ───────────────────────────────────────────────────────────────
    has_resume = bool(resume_text)
    has_company_info = bool(target_company)
    has_field_info = bool(target_field)

    # 레벨 3 구성
    level3_section = ""
    if has_field_info:
        level3_section = (
            f"■ 레벨 3: {target_field} 분야 최신 트렌드 적용 능력 (25%)\n"
            f"  - 2024년 {target_field} 분야의 최신 기술 동향에 대한 이해도\n"
            f"  - 현재 프로젝트에 최신 트렌드를 어떻게 적용할 수 있는지\n"
            f"  - 예: 'Kubernetes 대신 서버리스 아키텍처를 고려해보신 적 있나요?'\n\n"
        )
    else:
        level3_section = (
            "■ 레벨 3: 실전 장애 대응 능력 (30% - 압박 질문)\n"
            "  - 이 코드가 프로덕션 환경에서 어떤 문제를 일으킬 수 있는지\n"
            "  - 트래픽 100배 증가 시 어떻게 대응할 것인지\n\n"
        )

    # 레벨 4 구성
    level4_section = ""
    if has_company_info:
        level4_base = (
            f"■ 레벨 4: {target_company} 인재상 검증 (25%)\n"
            f"  - {target_company}의 인재상과 연결된 기술적/문화적 질문\n"
            f"  - 해당 기업의 면접 스타일에 맞춘 심층 질문\n"
        )
        
        if target_company == "업스테이지":
            level4_upstage = (
                "  - 업스테이지의 경우 Solar LLM, Document AI, Private LLM, RAG 시스템 등 최신 AI 기술에 대한 이해도 검증\n"
                "  - 예: 'Solar LLM을 이 프로젝트에 적용한다면 어떤 부분에서 성능 향상을 기대할 수 있을까요?'\n"
                "  - 예: '현재 코드에 RAG 시스템을 통합한다면 어떤 벡터 데이터베이스를 선택하시겠습니까?'\n"
                "  - 예: 'Document AI 기술로 이 데이터 처리 과정을 자동화한다면 어떤 점이 개선될까요?'\n\n"
            )
            level4_section = level4_base + level4_upstage
        else:
            level4_other = "  - 예: '사용자 중심 사고로 이 API를 어떻게 개선하시겠습니까?'\n\n"
            level4_section = level4_base + level4_other
    else:
        level4_section = (
            "■ 레벨 4: 실전 장애 대응 능력 (30% - 압박 질문)\n"
            "  - 이 코드가 프로덕션 환경에서 어떤 문제를 일으킬 수 있는지\n"
            "  - 트래픽 100배 증가 시 어떻게 대응할 것인지\n\n"
        )

    system_msg = (
        "당신은 IT 대기업의 10년 차 시니어 기술 면접관이자 코드 리뷰 전문가입니다. "
        "지원자의 GitHub 코드와 이력서를 철저히 교차 검증하여 '진짜 실력'을 가려내는 것이 목표입니다.\n\n"
        f"[지원자 기술 스택]\n{tech_stack or '정보 없음'}\n\n"
        f"{resume_context}\n\n"
        f"{company_context}\n\n"
        f"{field_context}\n\n"
        f"[제출된 GitHub 소스코드 문맥 (줄번호 포함)]\n{code_context}\n\n"
        "[질문 생성 전략]\n\n"
        "■ 레벨 1: 코드 표면 이해도 검증 (20%)\n"
        "  - 제출 코드의 특정 함수/클래스의 역할과 존재 이유\n"
        "  - 왜 이 라이브러리를 선택했는지\n"
        "  - 예: '23번째 줄의 async/await를 사용한 이유가 무엇인가요?'\n\n"
        "■ 레벨 2: 설계 의도 및 트레이드오프 파악 (30%)\n"
        "  - 이 구조를 선택한 이유와 버린 대안\n"
        "  - 성능·유지보수성·확장성 중 무엇을 우선했는지\n"
        "  - 예: 'FastAPI 대신 Django를 쓰지 않은 이유는? DRF와 비교했을 때 트레이드오프는?'\n\n"
        + level3_section
        + level4_section
        + (
            "■ 레벨 5: 이력서 교차 검증 (허수 걸러내기)\n"
            "  - 이력서: 'Redis 캐싱으로 성능 30% 개선' → 질문: '어떤 메트릭으로 측정했나요? 캐시 무효화 전략은?'\n"
            "  - 이력서: 'MSA 설계 경험' → 질문: '서비스 간 트랜잭션은 어떻게 처리하셨나요? Saga 패턴을 아시나요?'\n"
            "  - 이력서에 쓴 기술이 실제 코드에 없으면: '이력서에 Kafka 사용 경험을 작성하셨는데 이번 프로젝트엔 왜 안 쓰셨나요?'\n\n"
            if has_resume else
            "■ 레벨 5: 소스코드 심화 검증 (이력서 미제공 시)\n"
            "  - 코드에서 발견되는 잠재적 버그나 성능 문제 지적\n"
            "  - 예: '이 함수에서 N+1 쿼리 문제가 보이는데 인지하고 계셨나요?'\n\n"
        )
        + "■ 레벨 5: 깊이 있는 후속 질문 유도\n"
        "  - 단답형 불가능한 질문 (왜? 어떻게? 대안은?)\n"
        "  - 실패 경험 공유 유도 (디버깅 과정, 회고)\n"
        "  - 예: '이 코드를 6개월 후 다시 본다면 어떤 점을 리팩토링하고 싶으신가요?'\n\n"
        "[질문 구성 원칙]\n"
        "질문은 반드시 아래 두 가지 트랙을 혼합하여 생성하세요.\n\n"
        "■ 트랙 A — GitHub 소스코드 기반 질문 (source='code')\n"
        "  - 제출된 소스코드의 실제 구현을 파고드는 질문\n"
        "  - 코드 내 동시성/예외처리/성능/아키텍처 트레이드오프를 다루는 질문 최소 1개 포함\n"
        "  - 🔴🔴🔴 필수: 코드 기반 질문은 반드시 파일명과 줄 번호를 질문 텍스트에 포함하세요 🔴🔴🔴\n"
        "  - 🔴🔴🔴 필수: 질문에 파일명과 줄 번호가 포함되면 100% 확률로 file_path, start_line, end_line을 설정하세요 🔴🔴🔴\n"
        "  - 🔴🔴🔴 코드 하이라이팅 예시 (반드시 따라하세요): 🔴🔴🔴\n"
        "    • 질문: 'README.md 16-20번째 줄에 기술 스택이 기재되어 있습니다. FastAPI를 선택한 이유는?'\n"
        "      → file_path='README.md', start_line=16, end_line=20\n"
        "    • 질문: 'Danielle.html 8-15줄에는 NewJeans 멤버 네비게이션 바가 구현되어 있습니다...'\n"
        "      → file_path='Danielle.html', start_line=8, end_line=15\n"
        "    • 질문: 'app.py 25번째 줄에서 user_id를 하드코딩하고 있습니다...'\n"
        "      → file_path='app.py', start_line=25, end_line=25\n"
        "  - 🚨 코드 기반 질문 생성 규칙:\n"
        "    1. 질문 텍스트에 반드시 '[파일명] [줄번호]-[줄번호]' 또는 '[파일명] [줄번호]번째 줄' 형태로 명시\n"
        "    2. file_path는 실제 파일명과 정확히 일치\n"
        "    3. start_line, end_line은 1-based 인덱스\n"
        "    4. 단일 줄이면 start_line = end_line\n"
        "  - 전체 질문의 약 60% 비중\n\n"
        + (
            "■ 트랙 B — 이력서 프로젝트/경험 기반 질문 (source='resume')\n"
            "  - 이력서에 명시된 GitHub URL 이외의 다른 프로젝트, 인턴 경험, 수상 이력 등을 직접 파고드는 질문\n"
            "  - '이력서에 작성하셨는데 실제로 어떻게 구현하셨나요?', "
            "'그 프로젝트에서 가장 어려웠던 기술적 챌린지는 무엇이었나요?' 형태로 구체적으로 질문\n"
            "  - 이력서 주장과 실제 구현 능력 사이의 검증 질문 최소 1개 포함\n"
            "  - file_path는 null로 설정 (코드 무관)\n"
            "  - 전체 질문의 약 40% 비중\n\n"
            if has_resume else
            "■ 트랙 B — 이력서 미제공: 소스코드 분석 기반 질문으로 100% 구성\n\n"
        )
        + "[금지 사항]\n"
        "❌ 'RESTful API란 무엇인가요?' (단순 암기 질문)\n"
        "❌ 'Python과 JavaScript의 차이는?' (구글 검색으로 나오는 질문)\n"
        "❌ 코드에 없는 내용 상상해서 질문하기\n"
        "❌ 이력서에 없는 내용 상상해서 질문하기\n\n"
        "[좋은 질문 예시]\n"
        "✅ '이 프로젝트에서 Exception을 전혀 처리하지 않으셨는데, 실전에서 DB 연결이 끊기면 어떻게 대응하시겠습니까?'\n"
        "✅ '이력서에 Docker로 배포 자동화라고 쓰셨는데, 멀티 스테이지 빌드는 사용하셨나요? 이미지 크기는 얼마였나요?'\n"
        "✅ '코드에서 N+1 쿼리 문제가 보이는데 인지하고 계셨나요? 어떻게 해결하시겠습니까?'\n"
        "✅ 'README.md 16-20번째 줄에 기술 스택이 기재되어 있습니다. FastAPI를 선택한 이유는?' (file_path='README.md', start_line=16, end_line=20)\n"
    )
    
    # 업스테이지 예시 추가
    if target_company == "업스테이지":
        system_msg += (
            "✅ '업스테이지의 Solar LLM을 이 프로젝트에 통합한다면 어떤 모듈부터 개선하시겠습니까?'\n"
            "✅ '현재 구현된 로직에 RAG(Retrieval-Augmented Generation)를 적용한다면 벡터 데이터베이스는 어떤 것을 선택하시겠습니까?'\n"
            "✅ 'Document AI로 이 데이터 처리 파이프라인을 자동화한다면 정확도를 어떻게 측정하시겠습니까?'\n"
            "✅ 'Private LLM 환경에서 이 API를 배포한다면 보안과 성능 중 어느 것을 우선하시겠습니까?'\n"
        )
    
    system_msg += "\n"
    system_msg += (
        "1. 존재하지 않는 로직이나 이력서에 없는 내용을 상상해서 만들지 마세요.\n"
        "2. 단순 이론/정의 질문('REST API란?')은 절대 금지합니다.\n"
        "3. 🚨🚨🚨 코드 하이라이팅 필수 규칙 🚨🚨🚨\n"
        "   질문 내용에 특정 파일과 줄 번호를 언급할 때는 반드시 해당 정보를 metadata에 포함하세요:\n"
        "   - 질문 텍스트 예: 'README.md 16-20번째 줄에 기술 스택이...' \n"
        "     → file_path='README.md', start_line=16, end_line=20\n"
        "   - 질문 텍스트 예: 'app.py 25번째 줄에서 user_id를...' \n"
        "     → file_path='app.py', start_line=25, end_line=25\n"
        "   - 질문 텍스트 예: 'Danielle.html 8-15줄에는 네비게이션이...' \n"
        "     → file_path='Danielle.html', start_line=8, end_line=15\n"
        "4. 🔴 질문 텍스트에 파일명과 줄 번호가 포함되면 100% 확률로 file_path, start_line, end_line을 설정하세요.\n"
        "5. 질문은 정확히 5개만 생성하세요:\n"
        "   - Easy 난이도: 2개 (기초 개념 확인)\n"
        "   - Medium 난이도: 2개 (설계 의도 파악)\n"
        "   - Hard 난이도: 1개 (장애 대응·교차 검증)\n"
    )
    
    # 업스테이지 필수 조건 추가
    if target_company == "업스테이지":
        system_msg += "   - 🔥 업스테이지 선택 시 필수: 5개 질문 중 최소 2개는 LLM/RAG/Document AI 관련 질문으로 구성\n"
    
    system_msg += (
        "6. 모든 질문은 한국어 존댓말로 작성하세요.\n"
        "7. 첫 번째 질문은 반드시 Easy 난이도로 배치하세요.\n"
        "8. 🔥🔥🔥 코드 기반 질문(source='code')은 반드시 파일명과 줄 번호를 질문 텍스트에 포함하고 metadata를 설정하세요 🔥🔥🔥\n"
        "9. 파일 경로는 실제 존재하는 파일명과 정확히 일치해야 합니다.\n"
        "10. 🚨 코드 하이라이팅 검증:\n"
        "    - 질문에 'X파일 Y줄' 형태가 있으면 → file_path='X파일', start_line=Y, end_line=Y\n"
        "    - 질문에 'X파일 Y-Z줄' 형태가 있으면 → file_path='X파일', start_line=Y, end_line=Z\n"
        "    - 질문에 'X파일 Y번째 줄' 형태가 있으면 → file_path='X파일', start_line=Y, end_line=Y"
    )

    messages = [
        SystemMessage(content=system_msg),
        HumanMessage(content="위 소스코드와 이력서를 분석하여 두 트랙을 혼합한 면접 질문 풀을 생성해 주세요."),
    ]

    try:
        response = structured_llm.invoke(messages)
        question_pool = [
            {
                "question":   q.question,
                "source":     q.source,
                "file_path":  q.file_path,
                "start_line": q.start_line,
                "end_line":   q.end_line,
                "difficulty": q.difficulty,
            }
            for q in response.questions
        ]
    except Exception as e:
        # 풀 생성 실패 시 기본 질문 1개로 폴백
        question_pool = [
            {
                "question": (
                    "제출하신 프로젝트의 핵심 기술 선택 이유와 "
                    "해당 기술을 사용하면서 겪었던 가장 어려운 기술적 문제는 무엇이었나요?"
                ),
                "file_path": None,
                "start_line": None,
                "end_line": None,
                "difficulty": "easy",
            }
        ]
        print(f"[question_extractor] 질문 풀 생성 실패, 폴백 사용: {e}")

    print(f"[question_extractor] 질문 풀 {len(question_pool)}개 생성 완료")
    
    # 🏢 기업이 선택된 경우 첫 질문을 기업 지원 동기로 고정
    if has_company_info and target_company:
        company_motivation_question = {
            "question": f"{target_company}에 지원하게 된 동기와 이 회사에서 이루고 싶은 목표를 구체적으로 말씀해 주시겠습니까?",
            "source": "company",
            "file_path": None,
            "start_line": None,
            "end_line": None,
            "difficulty": "easy",
        }
        # 기업 동기 질문을 맨 앞에 추가
        question_pool.insert(0, company_motivation_question)
        print(f"[question_extractor] 기업 지원 동기 질문을 첫 질문으로 추가: {target_company}")
    
    # 🔴 하이라이팅 검증 및 보정
    for i, q in enumerate(question_pool):
        question_text = q.get("question", "")
        
        # 파일명과 줄 번호가 질문에 포함되어 있는지 검사
        import re
        
        # 패턴 1: "파일명 X-Y번째 줄" 또는 "파일명 X-Y줄"
        pattern1 = r'(\w+\.\w+)\s+(\d+)-(\d+)(?:번째\s+)?줄'
        match1 = re.search(pattern1, question_text)
        
        # 패턴 2: "파일명 X번째 줄"
        pattern2 = r'(\w+\.\w+)\s+(\d+)번째\s+줄'
        match2 = re.search(pattern2, question_text)
        
        # 패턴 3: "파일명 X-Y번째 줄"
        pattern3 = r'(\w+\.\w+)\s+(\d+)-(\d+)번째\s+줄'
        match3 = re.search(pattern3, question_text)
        
        if match1:
            file_name, start_str, end_str = match1.groups()
            q["file_path"] = file_name
            q["start_line"] = int(start_str)
            q["end_line"] = int(end_str)
            print(f"[하이라이팅 보정] {file_name} {start_str}-{end_str}줄 → file_path='{file_name}', start_line={start_str}, end_line={end_str}")
        elif match2:
            file_name, line_str = match2.groups()
            q["file_path"] = file_name
            q["start_line"] = int(line_str)
            q["end_line"] = int(line_str)
            print(f"[하이라이팅 보정] {file_name} {line_str}번째 줄 → file_path='{file_name}', start_line={line_str}, end_line={line_str}")
        elif match3:
            file_name, start_str, end_str = match3.groups()
            q["file_path"] = file_name
            q["start_line"] = int(start_str)
            q["end_line"] = int(end_str)
            print(f"[하이라이팅 보정] {file_name} {start_str}-{end_str}번째 줄 → file_path='{file_name}', start_line={start_str}, end_line={end_str}")

    # 🔴 첫 번째 질문은 반드시 Easy 난이도로 시작
    easy_questions = [q for q in question_pool if q.get("difficulty") == "easy"]
    other_questions = [q for q in question_pool if q.get("difficulty") != "easy"]
    
    if easy_questions:
        first = easy_questions[0]
        remaining_pool = easy_questions[1:] + other_questions
    else:
        # Easy 질문이 없으면 첫 번째 질문 사용
        first = question_pool[0] if question_pool else {}
        remaining_pool = question_pool[1:] if len(question_pool) > 1 else []
    
    first_question = first.get("question", "")
    first_highlight = None
    if first.get("file_path") and first.get("start_line") is not None:
        end = first.get("end_line") or first.get("start_line")
        if first["start_line"] <= end:
            first_highlight = {
                "file_path": first["file_path"],
                "start_line": first["start_line"],
                "end_line": end,
            }

    return {
        "question_pool": remaining_pool,
        "current_question": first_question,
        "current_highlight": first_highlight,
        "loop_count": 0,  # 🔴 0부터 시작 (첫 질문)
    }
