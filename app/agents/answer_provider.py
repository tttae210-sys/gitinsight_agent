"""
실시간 인터랙션 에이전트: AnswerProviderAgent
===============================================
역할: 지원자가 모범 답안을 직접 요청했을 때 완전한 해설을 제공하는 단일 책임 노드.
"""

from langchain_core.messages import SystemMessage, HumanMessage
from app.schemas import InterviewState
from app.core.llm import get_llm


def _pop_next_question_adaptive(state: InterviewState) -> tuple[str, dict | None, list]:
    """
    적응형 난이도로 question_pool에서 질문을 꺼냅니다.
    이전 답변의 점수를 기반으로 난이도를 조절합니다.
    """
    pool = list(state.get("question_pool", []))
    if not pool:
        return "", None, []
    
    evaluation = state.get("evaluation", {})
    last_score = evaluation.get("score", 5)
    
    # 🔴 적응형 난이도 판정
    if last_score <= 4:
        target_difficulty = "easy"
    elif last_score <= 7:
        target_difficulty = "medium"
    else:
        target_difficulty = "hard"
    
    # 🔴 난이도에 맞는 질문 선택
    selected_question = None
    remaining_pool = []
    
    for q in pool:
        if q.get("difficulty", "medium") == target_difficulty and not selected_question:
            selected_question = q
        else:
            remaining_pool.append(q)
    
    # 원하는 난이도가 없으면 풀의 첫 번째 질문 사용
    if not selected_question:
        selected_question = pool[0]
        remaining_pool = pool[1:]
    
    question = selected_question.get("question", "")
    highlight = None
    if selected_question.get("file_path") and selected_question.get("start_line") is not None:
        end = selected_question.get("end_line") or selected_question.get("start_line")
        if selected_question["start_line"] <= end:
            highlight = {
                "file_path": selected_question["file_path"],
                "start_line": selected_question["start_line"],
                "end_line": end,
            }
    
    return question, highlight, remaining_pool


def provide_answer(state: InterviewState) -> dict:
    """
    [실시간 에이전트] 모범 답안 제공 전담 노드
    
    3번 실패 후 자동 호출되거나, 사용자가 직접 정답 요청 시 호출됩니다.
    정답을 보여주고 자동으로 다음 질문으로 넘어갑니다.
    """
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
            "당신은 FAANG 출신의 시니어 개발자이자 기술 블로그 10만 팔로워를 보유한 테크 에반젤리스트입니다. "
            "지원자가 면접 질문의 모범 답안을 직접 요청했습니다. "
            "불필요한 인사말·칭찬·감탄사 없이 바로 핵심 해설로 시작하세요.\n\n"
            f"[프로젝트 소스코드 맥락]\n{code_context}\n\n"
            "[작성 지침]\n"
            "1. '안녕하세요', '멋진 질문이에요' 같은 인사로 시작하지 마세요.\n"
            "2. 핵심 개념과 원리 설명으로 바로 시작하세요.\n"
            "3. 소스코드를 기반으로 구체적인 예시를 들어 설명하세요.\n"
            "4. 필요하다면 코드 블록을 사용해도 됩니다.\n"
            "5. 트레이드오프와 대안 기술도 함께 언급하세요.\n"
            "6. 마지막에 관련 학습 키워드를 1~2개 짧게 제안하세요.\n"
            "7. 전체 내용은 간결하고 핵심만 담아 작성하세요.\n\n"
            "[모범 답안 구조]\n"
            "- 핵심 개념 설명 (2~3문장)\n"
            "- 실전 적용 예시 (코드 블록 또는 구체적 시나리오)\n"
            "- 트레이드오프·주의사항 (1~2문장)\n"
            "- 심화 학습 키워드 (1~2개)"
        )),
        HumanMessage(content=f"[면접 질문]\n{current_question}\n\n완전한 모범 답안을 알려주세요."),
    ]

    try:
        response    = llm.invoke(messages)
        answer_text = response.content.strip()
    except Exception as e:
        answer_text = f"모범 답안 생성 중 오류가 발생했습니다. ({e})"

    # 🔴 다음 질문 자동 꺼내기 (적응형 난이도)
    next_question, next_highlight, remaining_pool = _pop_next_question_adaptive(state)

    # 🔴 3번 실패 후 자동 호출된 경우 vs 사용자 직접 요청 경우 구분
    is_auto_fail = retry_count >= 3
    
    if is_auto_fail:
        feedback_prefix = "❌ **3번 실패로 인한 오답 처리**\n\n"
    else:
        feedback_prefix = "📖 **모범 답안**\n\n"

    result = {
        "current_question": next_question if next_question else "모든 질문이 종료되었습니다.",
        "current_highlight": next_highlight,
        "question_pool": remaining_pool,
        "retry_count": 0,  # 🔴 다음 질문으로 넘어가므로 retry_count 초기화
        "loop_count": state.get("loop_count", 1) + 1,
        "evaluation": {
            "score": 0,
            "passed": False,
            "reason": f"{feedback_prefix}{answer_text}"
        },
        "next_step": "NEXT_QUESTION_DONE" if next_question else "REPORT",
    }

    return result
