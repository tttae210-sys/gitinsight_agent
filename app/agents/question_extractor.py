"""
전처리 에이전트: QuestionExtractorAgent
========================================
역할: builder 노드가 GitHub 코드를 수집한 직후 단 한 번 실행됩니다.
     소스코드 + 이력서를 종합 분석하여 면접 질문 풀(question_pool)을 사전에 생성합니다.

실시간 인터랙션 에이전트들은 이 풀에서 질문을 꺼내어 사용하며,
턴마다 LLM을 호출해 질문을 새로 만들지 않아도 됩니다.
"""

from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from app.schemas import InterviewState
from app.core.llm import get_llm
from app.service.vector_service import get_vector_service


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

    for chunk in chunks:
        file_path = chunk.get("file_path", "unknown")
        code_text = chunk.get("content") or chunk.get("code", "")
        context += f"--- File: {file_path} ---\n"
        for idx, line in enumerate(code_text.split("\n"), 1):
            context += f"{idx}: {line}\n"
        context += "\n"

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
    - 소스코드 전체 + 이력서를 LLM에 한 번에 던져 5~7개의 질문을 미리 만들어둡니다.
    - 이후 실시간 인터랙션 에이전트(evaluator 흐름)는 이 풀에서 순서대로 꺼내씁니다.
    """
    llm = get_llm(temperature=0.8)
    structured_llm = llm.with_structured_output(QuestionPool)

    tech_stack = ", ".join(state.get("tech_stack", []))
    chunks = state.get("extracted_chunks", [])
    repo_url = state.get("repo_url", "")

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

    system_msg = (
        "당신은 IT 대기업의 10년 차 시니어 기술 면접관이자 코드 리뷰 전문가입니다. "
        "지원자의 GitHub 코드와 이력서를 철저히 교차 검증하여 '진짜 실력'을 가려내는 것이 목표입니다.\n\n"
        f"[지원자 기술 스택]\n{tech_stack or '정보 없음'}\n\n"
        f"{resume_context}\n\n"
        f"[제출된 GitHub 소스코드 문맥 (줄번호 포함)]\n{code_context}\n\n"
        "[질문 생성 전략]\n\n"
        "■ 레벨 1: 코드 표면 이해도 검증 (30%)\n"
        "  - 제출 코드의 특정 함수/클래스의 역할과 존재 이유\n"
        "  - 왜 이 라이브러리를 선택했는지\n"
        "  - 예: '23번째 줄의 async/await를 사용한 이유가 무엇인가요?'\n\n"
        "■ 레벨 2: 설계 의도 및 트레이드오프 파악 (40%)\n"
        "  - 이 구조를 선택한 이유와 버린 대안\n"
        "  - 성능·유지보수성·확장성 중 무엇을 우선했는지\n"
        "  - 예: 'FastAPI 대신 Django를 쓰지 않은 이유는? DRF와 비교했을 때 트레이드오프는?'\n\n"
        "■ 레벨 3: 실전 장애 대응 능력 (30% - 압박 질문)\n"
        "  - 이 코드가 프로덕션 환경에서 어떤 문제를 일으킬 수 있는지\n"
        "  - 트래픽 100배 증가 시 어떻게 대응할 것인지\n"
        "  - 예: 'DB 커넥션 풀이 고갈되면 어떤 증상이 나타나고 어떻게 디버깅하시겠습니까?'\n\n"
        + (
            "■ 레벨 4: 이력서 교차 검증 (허수 걸러내기)\n"
            "  - 이력서: 'Redis 캐싱으로 성능 30% 개선' → 질문: '어떤 메트릭으로 측정했나요? 캐시 무효화 전략은?'\n"
            "  - 이력서: 'MSA 설계 경험' → 질문: '서비스 간 트랜잭션은 어떻게 처리하셨나요? Saga 패턴을 아시나요?'\n"
            "  - 이력서에 쓴 기술이 실제 코드에 없으면: '이력서에 Kafka 사용 경험을 작성하셨는데 이번 프로젝트엔 왜 안 쓰셨나요?'\n\n"
            if has_resume else
            "■ 레벨 4: 소스코드 심화 검증 (이력서 미제공 시)\n"
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
        "  - 연관 코드가 있으면 file_path, start_line, end_line을 정확히 지정 (1~15줄 범위)\n"
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
        "✅ '코드에서 N+1 쿼리 문제가 보이는데 인지하고 계셨나요? 어떻게 해결하시겠습니까?'\n\n"
        "[공통 원칙]\n"
        "1. 존재하지 않는 로직이나 이력서에 없는 내용을 상상해서 만들지 마세요.\n"
        "2. 단순 이론/정의 질문('REST API란?')은 절대 금지합니다.\n"
        "3. 질문은 정확히 5개만 생성하세요:\n"
        "   - Easy 난이도: 2개 (기초 개념 확인)\n"
        "   - Medium 난이도: 2개 (설계 의도 파악)\n"
        "   - Hard 난이도: 1개 (장애 대응·교차 검증)\n"
        "4. 모든 질문은 한국어 존댓말로 작성하세요.\n"
        "5. 첫 번째 질문은 반드시 Easy 난이도로 배치하세요."
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
