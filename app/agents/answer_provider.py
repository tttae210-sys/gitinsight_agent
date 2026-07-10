"""
실시간 인터랙션 에이전트: AnswerProviderAgent
===============================================
역할: 지원자가 모범 답안을 직접 요청했을 때 완전한 해설을 제공하는 단일 책임 노드.
"""

from langchain_core.messages import SystemMessage, HumanMessage
from app.schemas import InterviewState
from app.core.llm import get_llm


def _pop_next_question(state: InterviewState) -> tuple[str, dict | None, list]:
    """question_pool의 첫 번째 항목을 꺼내 (question, highlight, remaining_pool)을 반환합니다."""
    pool = list(state.get("question_pool", []))
    if not pool:
        return "", None, []
    next_q   = pool.pop(0)
    question = next_q.get("question", "")
    highlight = None
    if next_q.get("file_path") and next_q.get("start_line") is not None:
        end = next_q.get("end_line") or next_q.get("start_line")
        if next_q["start_line"] <= end:
            highlight = {
                "file_path":  next_q["file_path"],
                "start_line": next_q["start_line"],
                "end_line":   end,
            }
    return question, highlight, pool


def provide_answer(state: InterviewState) -> dict:
    """[실시간 에이전트] 모범 답안 제공 전담 노드"""
    llm = get_llm(temperature=0.3)

    current_question = state.get("current_question", "")
    chunks           = state.get("extracted_chunks", [])
    retry_count      = state.get("retry_count", 0)

    code_context = ""
    for chunk in chunks:
        code_context += (
            f"--- File: {chunk.get('file_path')} ---\n"
            f"{chunk.get('content', chunk.get('code', ''))}\n\n"
        )
    code_context = code_context or "분석 대상 소스코드가 없습니다."

    # SystemMessage/HumanMessage 직접 사용 — ChatPromptTemplate 파싱 완전 우회
    messages = [
        SystemMessage(content=(
            "당신은 IT 대기업 출신의 시니어 개발자 멘토입니다.\n"
            "지원자가 면접 질문의 모범 답안을 직접 요청했습니다. "
            "불필요한 인사말·칭찬·감탄사 없이 바로 핵심 해설로 시작하세요.\n\n"
            f"[프로젝트 소스코드 맥락]\n{code_context}\n\n"
            "[작성 지침]\n"
            "1. '안녕하세요', '멋진 질문이에요' 같은 인사로 시작하지 마세요.\n"
            "2. 핵심 개념과 원리 설명으로 바로 시작하세요.\n"
            "3. 소스코드를 기반으로 구체적인 예시를 들어 설명하세요.\n"
            "4. 필요하다면 코드 블록을 사용해도 됩니다.\n"
            "5. 마지막에 관련 학습 키워드를 1~2개 짧게 제안하세요.\n"
            "6. 전체 내용은 간결하고 핵심만 담아 작성하세요."
        )),
        HumanMessage(content=f"[면접 질문]\n{current_question}\n\n완전한 모범 답안을 알려주세요."),
    ]

    try:
        response    = llm.invoke(messages)
        answer_text = response.content.strip()
    except Exception as e:
        answer_text = f"모범 답안 생성 중 오류가 발생했습니다. ({e})"

    next_question, next_highlight, remaining_pool = _pop_next_question(state)

    result = {
        "evaluation":    {"score": 0, "passed": False, "reason": f"📖 **모범 답안**\n\n{answer_text}"},
        "next_step":     "ANSWER_GIVEN",
        "retry_count":   min(retry_count + 1, 3),
        "question_pool": remaining_pool,
    }
    if next_question:
        result["current_question"]  = next_question
        result["current_highlight"] = next_highlight
        result["loop_count"]        = state.get("loop_count", 1) + 1
    return result
