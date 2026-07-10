"""
실시간 인터랙션 에이전트: EvaluatorAgent
==========================================
역할: 지원자의 답변을 채점하는 단일 책임 노드.

- 포기/힌트 요청/정답 요청은 빠른 규칙 기반으로 먼저 분기
- 실제 기술 답변은 LLM 구조화 출력으로 정밀 채점
- 채점 결과(passed, score, reason)와 next_step만 반환 — 힌트 생성·리포트는 다른 에이전트 담당
"""

from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from app.schemas import InterviewState
from app.core.llm import get_llm


# ──────────────────────────────────────────────────────────────────────────────
# 0. 구조화 출력 스키마
# ──────────────────────────────────────────────────────────────────────────────

class EvaluationResult(BaseModel):
    score: int = Field(description="지원자 답변 점수 (1~10)")
    passed: bool = Field(
        description=(
            "핵심 요구사항을 충족했는지 여부. "
            "'모르겠다', '힌트 달라', '패스' 등 포기 표현은 무조건 False."
        )
    )
    reason: str = Field(
        description=(
            "채점 근거 피드백. 잘한 점 → 부족한 점 순서로 5문장 이내 작성. "
            "코드 블록 사용 금지, 함수명·변수명은 문장 안에 자연어로 풀어 쓸 것."
        )
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. 입력 분류 헬퍼
# ──────────────────────────────────────────────────────────────────────────────

_STRONG_GIVEUP  = ["모르겠", "모릅니다", "몰라요", "패스", "pass"]
_HINT_REQUEST   = ["힌트 주세요", "힌트를 줘", "힌트 줘", "힌트좀", "힌트 좀", "알려줘요"]
_ANSWER_REQUEST = [
    "정답이 뭐", "답이 뭐", "답을 알려", "정답 알려", "정답을 알려",
    "답 알려줘", "정답 줘", "정답을 줘", "답 줘", "모범 답안",
    "답 알려", "정답 알려줘", "답알려줘", "정답알려줘",
]
_WEAK_SIGNALS   = ["어렵다", "어려워", "어려운", "도와줘"]


def _classify_input(user_answer: str) -> str:
    """빠른 규칙 기반 입력 분류 → 'ANSWER_REQUEST' | 'SURRENDER' | 'TECHNICAL'"""
    if any(kw in user_answer for kw in _ANSWER_REQUEST):
        return "ANSWER_REQUEST"
    is_too_short      = len(user_answer) < 5
    has_strong_giveup = any(kw in user_answer for kw in _STRONG_GIVEUP)
    has_hint_request  = any(kw in user_answer for kw in _HINT_REQUEST)
    has_weak_only     = any(kw in user_answer for kw in _WEAK_SIGNALS) and len(user_answer) < 15
    if is_too_short or has_strong_giveup or has_hint_request or has_weak_only:
        return "SURRENDER"
    return "TECHNICAL"


# ──────────────────────────────────────────────────────────────────────────────
# 2. 채점 노드
# ──────────────────────────────────────────────────────────────────────────────

def evaluate_answer(state: InterviewState) -> dict:
    """
    [실시간 에이전트] 채점 전담 노드

    next_step 반환 규칙:
      ANSWER_REQUEST → answer_provider
      SURRENDER      → hint_agent (retry_count 유지 — 오답 처리 안 함)
      PASS           → next_question (retry_count 초기화)
      HINT           → hint_agent (retry_count 증가)
      FAIL           → reporter (3-Strike 아웃)
    """
    tech_stack       = ", ".join(state.get("tech_stack", []))
    current_question = state.get("current_question", "이전 질문이 존재하지 않습니다.")
    answer_history   = state.get("answer_history", [])
    user_answer      = answer_history[-1].strip() if answer_history else ""
    retry_count      = state.get("retry_count", 0)
    chunks           = state.get("extracted_chunks", [])

    input_type = _classify_input(user_answer)

    if input_type == "ANSWER_REQUEST":
        return {
            "evaluation":  {"score": 0, "passed": False, "reason": ""},
            "next_step":   "ANSWER_REQUEST",
            "retry_count": min(retry_count + 1, 3),
        }

    if input_type == "SURRENDER":
        return {
            "evaluation": {
                "score": 0,
                "passed": False,
                "reason": "모르겠다고 하셨군요. 괜찮아요! 힌트 에이전트가 소스코드에서 단서를 짚어드릴게요.",
            },
            "next_step":   "HINT",
            "retry_count": retry_count,  # 오답 처리 안 함
        }

    # ── LLM 정밀 채점 ──────────────────────────────────────────────────────────
    llm = get_llm(temperature=0.0)
    structured_llm = llm.with_structured_output(EvaluationResult)

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
            "당신은 컴퓨터공학과 학생을 대상으로 기술 면접을 진행하는 "
            "IT 대기업의 정교하고 날카로운 시니어 면접관입니다.\n\n"
            f"[지원자 기술 스택]\n{tech_stack or '정보 없음'}\n\n"
            f"[지원자 프로젝트 소스코드]\n{code_context}\n\n"
            "[채점 루브릭]\n"
            "- 1~3점: 핵심을 전혀 짚지 못하거나 기술적으로 명백히 틀린 경우\n"
            "- 4~6점: 방향은 맞지만 구체적 근거/구현 디테일 부족\n"
            "- 7점  : 핵심 개념은 맞지만 실전 레벨 디테일 부족 (원칙적 불합격)\n"
            "- 8~10점: 원리·트레이드오프를 정확히 설명하고 구체적 해결책까지 제시 (합격)\n\n"
            "[피드백 작성 규칙]\n"
            "1. 잘한 점 → 부족한 점 순서로 5문장 이내.\n"
            "2. 코드 블록 사용 금지. 함수명은 자연어 문장 안에 녹여 쓸 것.\n"
            "3. 불합격 시 정답을 직접 말하지 말고 소크라테스식 힌트 방향만 제시.\n"
            "4. 합격 시 한 단계 심화 개념을 짧게 언급하며 격려."
        )),
        HumanMessage(content=(
            f"[면접 질문]\n{current_question}\n\n"
            f"[지원자 답변]\n{user_answer}\n\n"
            "정밀 채점 결과(점수, 통과여부, 피드백)를 반환해 주세요."
        )),
    ]

    try:
        response = structured_llm.invoke(messages)
        evaluation = {"score": response.score, "passed": response.passed, "reason": response.reason}
    except Exception as e:
        evaluation = {"score": 5, "passed": False, "reason": f"채점 중 오류가 발생했습니다. ({e})"}

    # 3-Strike 아웃 판정
    if evaluation["passed"]:
        next_step = "PASS"
        new_retry = 0
    else:
        new_retry = retry_count + 1
        if new_retry >= 3:
            next_step = "FAIL"
            evaluation["reason"] = "❌ **3-Strike 아웃**\n\n" + evaluation["reason"]
        else:
            next_step = "HINT"

    return {"evaluation": evaluation, "next_step": next_step, "retry_count": new_retry}
