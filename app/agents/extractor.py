from typing import Optional
from pydantic import BaseModel, Field
from app.schemas import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm
from app.service.vector_service import get_vector_service


class ExtractedQuestionSchema(BaseModel):
    question: str = Field(description="지원자에게 던질 구체적인 꼬리 질문 또는 힌트 메시지")
    file_path: Optional[str] = Field(None, description="질문 중 언급하거나 지적한 소스코드의 파일 경로")
    start_line: Optional[int] = Field(None, description="지적한 코드 영역의 시작 줄 번호 (1부터 시작)")
    end_line: Optional[int] = Field(None, description="지적한 코드 영역의 끝 줄 번호 (1부터 시작)")


def _build_code_context(chunks: list, rag_chunks: list) -> str:
    """state 청크 + RAG 검색 결과를 줄번호 포함 텍스트로 조합합니다."""
    code_context = ""

    for chunk in chunks:
        file_path = chunk.get("file_path", "unknown")
        code_text = chunk.get("content") or chunk.get("code", "")
        code_context += f"--- File: {file_path} ---\n"
        for idx, line in enumerate(code_text.split("\n"), 1):
            code_context += f"{idx}: {line}\n"
        code_context += "\n"

    for i, rc in enumerate(rag_chunks, start=1):
        file_path = rc.get("file_path", "unknown")
        code_text = rc.get("content", "")
        code_context += f"--- [RAG #{i}] File: {file_path} ---\n"
        for idx, line in enumerate(code_text.split("\n"), 1):
            code_context += f"{idx}: {line}\n"
        code_context += "\n"

    return code_context.strip() or "제출된 소스코드에 분석 가능한 주요 코드 파일이 존재하지 않습니다."


def _parse_highlight(response) -> Optional[dict]:
    """LLM 응답에서 하이라이트 메타데이터를 안전하게 추출합니다."""
    if not response.file_path or response.start_line is None:
        return None
    end_line = response.end_line if response.end_line is not None else response.start_line
    if response.start_line > end_line:
        return None
    return {
        "file_path": response.file_path,
        "start_line": response.start_line,
        "end_line": end_line
    }


def extract_interview_question(state: InterviewState) -> dict:
    """
    수집된 소스코드 문맥에 라인 번호를 명시하고,
    LLM을 통해 질문(또는 힌트)과 하이라이트 메타데이터를 함께 추출합니다.

    - next_step == "HINT": 모르겠다고 한 직후 → 힌트 + 코드 지목 제공
    - 그 외: 이력서와 소스코드 정합성을 교차 검증하는 새 면접 질문 생성
    """
    llm = get_llm(temperature=0.4)
    structured_llm = llm.with_structured_output(ExtractedQuestionSchema)

    tech_stack = ", ".join(state.get("tech_stack", []))
    loop_count = state.get("loop_count", 0)
    chunks = state.get("extracted_chunks", [])
    repo_url = state.get("repo_url", "")
    answer_history = state.get("answer_history", [])
    next_step = state.get("next_step", "")
    current_question = state.get("current_question", "")
    evaluation = state.get("evaluation", {})

    # ── [핵심] LangGraph 상태에서 이력서 텍스트 획득 및 포맷팅 ─────────────────────
    resume_text = state.get("resume_text", "")
    if resume_text:
        # 이력서 텍스트 내 중괄호를 이스케이프 → LangChain 템플릿 변수 오인 방지
        safe_resume = resume_text.replace("{", "{{").replace("}", "}}")
        resume_context = (
            f"--- [지원자 이력서 내용 (Resume)] ---\n"
            f"{safe_resume}\n"
            f"------------------------------------"
        )
    else:
        resume_context = "제공된 이력서가 없습니다. (소스코드 분석 중심의 기본 기술 질문으로 전향하세요.)"

    # ── RAG 검색 ──────────────────────────────────────────────────────────────
    recent_answer = answer_history[-1] if answer_history else ""
    rag_query = f"{tech_stack} {recent_answer}".strip() or "코드 구조 및 설계"

    try:
        rag_chunks = get_vector_service().search(
            query=rag_query,
            filters={"repo_url": repo_url} if repo_url else None,
            n_results=3,
        )
    except Exception:
        rag_chunks = []
    print(f"[extractor] RAG 검색: {len(rag_chunks)}개 | query: '{rag_query[:50]}'")
    # ──────────────────────────────────────────────────────────────────────────

    code_context = _build_code_context(chunks, rag_chunks)

    # 이전 대화 기록 포맷팅
    history_conversation = ""
    for idx, chat in enumerate(answer_history):
        role = "지원자" if idx % 2 != 0 else "면접관"
        history_conversation += f"- {role}: {chat}\n"
    if not history_conversation:
        history_conversation = "(아직 대화 기록이 없습니다. 이번이 첫 질문입니다.)"

    # ── HINT 모드: 모르겠다고 한 직후 → 힌트 + 코드 지목 ─────────────────────
    if next_step == "HINT":
        hint_reason = evaluation.get("reason", "")

        hint_system_msg = (
            "당신은 지원자가 기술 면접 질문에 답하지 못했을 때, "
            "정답을 직접 알려주지 않고 소크라테스식으로 스스로 답을 찾도록 유도하는 시니어 개발자 멘토입니다.\n\n"
            f"[직전 면접 질문]\n{current_question}\n\n"
            f"[지원자 답변 평가 결과]\n{hint_reason}\n\n"
            "[프로젝트 소스코드 문맥 (줄번호 포함)]\n"
            "{code_context}\n\n"
            "[힌트 생성 원칙 - 매우 중요]\n"
            "1. 절대로 코드를 그대로 인용하거나 코드 블록(```...```)을 사용하지 마세요.\n"
            "2. 소스코드에서 힌트가 될 부분을 찾았다면, 그 내용을 자연어로 풀어서 설명하세요.\n"
            "   예시) '14번째 줄에서 HTTP 요청을 반복문 안에서 매번 새로 열고 있는 부분을 살펴보세요. "
            "이런 패턴이 트래픽이 몰릴 때 어떤 문제를 만들 수 있을지 생각해보세요.'\n"
            "3. 정답을 직접 말하지 마세요. 지원자가 스스로 생각할 수 있는 질문 형태로 유도하세요.\n"
            "4. 따뜻하고 격려하는 어조로, 지원자가 좌절하지 않도록 응원의 말도 한 마디 담아주세요.\n"
            "5. 힌트는 반드시 한 가지만 제공하고, 전체 내용을 3~5문장 이내로 간결하게 작성하세요."
        )

        hint_prompt = ChatPromptTemplate.from_messages([
            ("system", hint_system_msg),
            ("human", "지원자가 답을 모르겠다고 했습니다. 소스코드에서 힌트 영역을 지목하고 단계적 힌트를 제공해 주세요.")
        ])

        chain = hint_prompt | structured_llm
        response = chain.invoke({"code_context": code_context})

        return {
            "current_question": f"💡 **힌트**\n\n{response.question}",
            "current_highlight": _parse_highlight(response),
            "loop_count": loop_count   # 힌트 제공 시엔 loop_count 증가 안 함
        }
    # ──────────────────────────────────────────────────────────────────────────

    # ── 일반 모드: 이력서와 깃허브 소스코드를 결합한 새 면접 질문 생성 ──────────────
    # 조원분의 f-string 및 일반 문자열 암묵적 결합 스타일을 보존하면서 이력서 컨텍스트를 주입합니다.
    system_msg = (
        "당신은 강원대학교 컴퓨터공학과 학생들을 대상으로 실전 압박 기술 면접을 진행하는 "
        "IT 대기업의 10년 차 시니어 개발자 면접관입니다. 당신의 목표는 지원자가 제출한 "
        "이력서 정보(주장)와 실제 프로젝트 소스 코드(증거)를 철저히 교차 대조하여, "
        "단순 검색으로는 답할 수 없는 날카롭고 구체적인 압박 질문을 던지는 것입니다.\n\n"
        f"[지원자 기술 스택]\n{tech_stack if tech_stack else '정보 없음'}\n\n"
        f"{resume_context}\n\n"  # 📄 [이력서 주입]: 이력서 내 중괄호가 템플릿 컴파일을 깨뜨리지 않게 선행 바인딩 처리!
        f"[현재까지 진행된 질문 횟수]\n{loop_count}회 (횟수가 늘어날수록 질문 난이도를 "
        "점진적으로 아키텍처/트레이드오프 및 구현 정합성 검증 수준까지 심화시키세요)\n\n"
        "[프로젝트 소스코드 문맥 (줄번호 포함)]\n"
        "{code_context}\n\n"
        "[이전 면접 대화 기록 - 중복 질문 방지용 참고자료]\n"
        "{history_conversation}\n\n"
        "[질문 생성 및 교차 검증 원칙]\n"
        "1. 반드시 위 [프로젝트 소스코드 문맥]과 [지원자 이력서 내용]의 매핑 지점을 정교하게 파고드세요.\n"
        "   - 이력서에 작성된 주요 기술 역량이나 경험적 성과가 실제 코드베이스에 어떻게 녹아있는지 대조하여 유효성을 검증하세요.\n"
        "   - 이력서의 주장과 실제 구현 코드 사이의 기술적 괴리가 보인다면(예: 이력서엔 대규모 최적화를 적어뒀으나 코드엔 기본 모듈만 방치된 경우) "
        "그 괴리에 담긴 트레이드오프나 한계를 짚어주는 예리한 질문을 던지세요.\n"
        "2. 소스코드나 이력서에 실존하지 않는 로직이나 무관한 개념을 상상해서 지어내지 마세요.\n"
        "3. 단순 이론이나 단순 정의(예: 'REST API가 뭔가요?')를 묻는 질문은 절대 금지합니다.\n"
        "   - 권장: '이력서에서 대량 트래픽 최적화를 위해 Redis 분산 캐시 정합성을 확보했다고 명시하셨는데, "
        "File: main.py 24줄을 보니 여전히 싱글 머신 로컬 메모리 저장소를 사용 중이십니다. 이 부분의 구현상 한계를 어떻게 극복하실 계획인가요?'\n"
        "4. 이미 나눴던 주제는 가급적 피하고 코드 및 이력서의 다른 새로운 도메인 영역에서 질문을 발굴하세요.\n"
        "5. 직전 답변에서 오개념이 확인된다면 해당 오답 논리를 파고드는 날카로운 꼬리 질문으로 흐름을 확장하세요.\n"
        "6. 질문은 반드시 한 번에 단 하나만 던지세요.\n\n"
        "[하이라이트(코드 지목) 규칙]\n"
        "1. 질문과 연관된 코드가 있다면 file_path, start_line, end_line을 함께 지정하세요.\n"
        "2. 줄 번호는 위 소스코드 문맥의 실제 줄 번호와 정확히 일치해야 합니다.\n"
        "3. 지목 범위는 1~15줄 이내로 좁혀서 지정하세요.\n"
        "4. 관련 코드가 없는 질문이거나 순수 이력서 기반 종합 질문이라면 null(None)로 반환하세요.\n\n"
        "[출력 형식]\n"
        "자연스럽고 정중한 한국어 존댓말로, 사족 없이 질문의 핵심만 작성하세요."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", "위 문맥과 대화 기록을 이어받아, 다음 면접 질문과 하이라이트 영역을 구성해 주세요.")
    ])

    chain = prompt | structured_llm
    response = chain.invoke({
        "code_context": code_context,
        "history_conversation": history_conversation
    })

    return {
        "current_question": response.question,
        "current_highlight": _parse_highlight(response),
        "loop_count": loop_count + 1
    }