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
    - 그 외: 새 면접 질문 생성
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

    # 이전 대화 기록
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
            "[힌트 생성 원칙]\n"
            "1. 정답을 직접 말하지 마세요. '이 부분을 보세요', '이 키워드를 생각해보세요' 수준으로 유도하세요.\n"
            "2. 소스코드에서 힌트가 될 수 있는 특정 코드 영역을 지목하고, "
            "그 코드를 보면서 스스로 생각해볼 수 있는 질문 형태로 힌트를 제공하세요.\n"
            "3. 따뜻하고 격려하는 어조로, 지원자가 좌절하지 않도록 응원의 말도 한 마디 담아주세요.\n"
            "4. 힌트는 반드시 한 가지만 제공하세요."
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

    # ── 일반 모드: 새 면접 질문 생성 ──────────────────────────────────────────
    system_msg = (
        "당신은 강원대학교 컴퓨터공학과 학생들을 대상으로 실전 압박 기술 면접을 진행하는 "
        "IT 대기업의 10년 차 시니어 개발자 면접관입니다. 당신의 목표는 지원자가 제출한 "
        "실제 프로젝트 소스 코드를 근거로, 단순 검색으로는 답할 수 없는 날카롭고 구체적인 "
        "꼬리 질문을 던지는 것입니다.\n\n"
        f"[지원자 기술 스택]\n{tech_stack if tech_stack else '정보 없음'}\n\n"
        f"[현재까지 진행된 질문 횟수]\n{loop_count}회 (횟수가 늘어날수록 질문 난이도를 "
        "점진적으로 아키텍처/트레이드오프 수준까지 심화시키세요)\n\n"
        "[프로젝트 소스코드 문맥 (줄번호 포함)]\n"
        "{code_context}\n\n"
        "[이전 면접 대화 기록 - 중복 질문 방지용 참고자료]\n"
        "{history_conversation}\n\n"
        "[질문 생성 원칙]\n"
        "1. 반드시 위 [프로젝트 소스코드 문맥]에 실제로 존재하는 함수, 로직, 변수명, 라이브러리 "
        "사용 방식에 근거하여 질문하세요. 코드에 없는 내용을 상상하거나 지어내지 마세요.\n"
        "2. 단순 정의를 묻는 질문은 절대 금지합니다.\n"
        "   - 금지: '객체지향이 뭔가요?', 'REST API가 뭔가요?'\n"
        "   - 권장: '이 파일에서 반복문 안에서 매번 새로운 DB 커넥션을 여는데, "
        "트래픽이 몰리면 어떤 문제가 발생하고 어떻게 개선하시겠어요?'\n"
        "3. '왜 이렇게 설계했는지', '이 로직의 문제점', '트레이드오프' 중 하나 이상 포함하세요.\n"
        "4. 이미 나왔던 주제는 피하고 코드의 다른 영역에서 새로운 질문을 던지세요.\n"
        "5. 직전 답변에서 잘못 이해한 부분이 보이면 그 오개념을 짚는 후속 질문으로 이어가세요.\n"
        "6. 질문은 반드시 하나만 던지세요.\n\n"
        "[하이라이트(코드 지목) 규칙]\n"
        "1. 질문과 연관된 코드가 있다면 file_path, start_line, end_line을 함께 지정하세요.\n"
        "2. 줄 번호는 위 소스코드 문맥의 실제 줄 번호와 정확히 일치해야 합니다.\n"
        "3. 지목 범위는 1~15줄 이내로 좁혀서 지정하세요.\n"
        "4. 관련 코드가 없는 질문이라면 null(None)로 반환하세요.\n\n"
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
