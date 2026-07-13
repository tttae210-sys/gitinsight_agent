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
    technical_understanding: int = Field(
        description="기술 이해도 점수 (1~10): 기본 개념, 원리, 구조에 대한 이해 정도"
    )
    problem_solving: int = Field(
        description="문제 해결 능력 점수 (1~10): 트레이드오프 분석, 실전 적용, 장애 대응 능력"
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
    """빠른 규칙 기반 입력 분류 → 'ANSWER_REQUEST' | 'QUESTION_REQUEST' | 'SURRENDER' | 'TECHNICAL'"""
    
    # 🔴 "질문해달라" 같은 질문 요청은 별도 분류 (힌트와 구분)
    question_request_keywords = [
        "질문해", "질문 해", "질문좀", "질문 좀", "질문해줘", "질문 해줘",
        "물어봐", "물어봐줘", "면접 시작", "면접 질문", "질문 주세요", "질문 줘",
        "면접해", "면접해줘", "면접 질문해", "면접 질문해줘"
    ]
    
    # 🔴 순수 질문 요청인지 확인 (기술적 내용 없이 질문만 요청)
    is_question_request = any(kw in user_answer.lower() for kw in question_request_keywords)
    has_no_technical_content = len(user_answer) < 50 and not any(tech_word in user_answer.lower() for tech_word in [
        "api", "데이터베이스", "함수", "클래스", "변수", "코드", "로직", "알고리즘", 
        "성능", "최적화", "버그", "에러", "디버깅", "테스트", "배포", "서버",
        "프레임워크", "라이브러리", "패턴", "구조", "설계", "아키텍처"
    ])
    
    if is_question_request and has_no_technical_content:
        return "QUESTION_REQUEST"
    
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
      FINAL_REPORT   → reporter (5번째 질문 완료 후 최종 리포트)
    """
    tech_stack       = ", ".join(state.get("tech_stack", []))
    current_question = state.get("current_question", "이전 질문이 존재하지 않습니다.")
    answer_history   = state.get("answer_history", [])
    user_answer      = answer_history[-1].strip() if answer_history else ""
    retry_count      = state.get("retry_count", 0)
    chunks           = state.get("extracted_chunks", [])
    loop_count       = state.get("loop_count", 0)
    
    # 🏢 기업 동기 질문인 경우 자동 통과
    target_company = state.get("target_company", "")
    if target_company and "지원하게 된 동기" in current_question:
        return {
            "evaluation": {
                "score": 10,
                "passed": True,
                "reason": f"환영합니다! {target_company}에 대한 열정이 느껴지네요. 그럼 이제 기술 면접을 시작하겠습니다.",
                "technical_understanding": 10,
                "problem_solving": 10,
            },
            "next_step": "PASS",
            "retry_count": 0,
        }

    input_type = _classify_input(user_answer)

    # 🔴 질문 요청인 경우 → 현재 질문 그대로 유지하고 CHAT으로 분기
    if input_type == "QUESTION_REQUEST":
        return {
            "evaluation": {
                "score": 0,
                "passed": False,
                "reason": "질문을 다시 확인해주세요.",
                "technical_understanding": 0,
                "problem_solving": 0,
            },
            "next_step": "QUESTION_REPEAT",  # 새로운 분기
            "retry_count": retry_count,  # 기존 retry_count 유지
        }

    if input_type == "ANSWER_REQUEST":
        return {
            "evaluation":  {
                "score": 0,
                "passed": False,
                "reason": "",
                "technical_understanding": 0,
                "problem_solving": 0,
            },
            "next_step":   "ANSWER_REQUEST",
            "retry_count": min(retry_count + 1, 3),
        }

    if input_type == "SURRENDER":
        new_retry = retry_count + 1
        evaluation = {
            "score": 0,
            "passed": False,
            "reason": "모르겠다고 하셨군요. 힌트를 드릴게요. 힌트를 참고해서 다시 도전해보세요!",
            "technical_understanding": 0,
            "problem_solving": 0,
        }
        # 🔴 3번 포기하면 정답 제공, 아니면 HINT로 라우팅
        if new_retry >= 3:
            next_step = "ANSWER_REQUEST"
            evaluation["reason"] = (
                "❌ **3번 모두 포기하셨습니다.**\n\n"
                "이 질문은 불합격 처리되며, 모범 답안을 보여드린 후 다음 질문으로 넘어갑니다."
            )
        else:
            next_step = "HINT"
        return {
            "evaluation": evaluation,
            "next_step":  next_step,
            "retry_count": new_retry,
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
            "당신은 FAANG(Facebook/Meta, Amazon, Apple, Netflix, Google) 출신으로 "
            "10년 이상 시니어 개발자로 근무하며 1000명 이상의 후배를 면접해 본 "
            "냉철하고 날카로운 기술 면접관입니다.\n\n"
            f"[지원자 기술 스택]\n{tech_stack or '정보 없음'}\n\n"
            f"[지원자 프로젝트 소스코드]\n{code_context}\n\n"
            "[면접 철학]\n"
            "- 표면적 지식보다 '왜'를 5번 물어 근본 원리 이해도를 파악합니다\n"
            "- '일단 동작하면 됩니다'식 답변은 즉시 간파합니다\n"
            "- 트레이드오프를 말하지 못하면 실무 경험 부족으로 판단합니다\n"
            "- 코드는 거짓말하지 않습니다 — 이력서 주장과 코드 실력의 괴리를 날카롭게 짚어냅니다\n\n"
            "[채점 원칙]\n"
            "- 단순 암기 답변 vs 경험 기반 답변을 구분합니다\n"
            "- '~인 것 같아요' → 감점 (불확실성)\n"
            "- '~때문에 ~를 선택했습니다' → 가점 (의사결정 근거)\n"
            "- 실패 사례를 솔직히 말하는 지원자를 높이 평가합니다\n\n"
            "[불합격 신호]\n"
            "1. 공식 문서를 읽어본 적 없는 것처럼 보이는 답변\n"
            "2. 예외 처리·동시성·확장성을 전혀 고려하지 않는 답변\n"
            "3. '항상 이렇게 해왔어요'만 반복하고 이유를 모르는 경우\n"
            "4. 자신의 코드에서 발견되는 명백한 문제점을 인지하지 못하는 경우\n\n"
            "[합격 신호]\n"
            "1. A를 선택한 이유와 B를 버린 이유를 명확히 설명\n"
            "2. 본인 코드의 약점을 인지하고 개선 방향까지 제시\n"
            "3. 실무에서 겪은 구체적 장애 사례와 해결 과정 언급\n"
            "4. '이 부분은 아직 모릅니다' 솔직한 인정 + 학습 의지 표현\n\n"
            "[점수 산정 루브릭]\n"
            "- 1~3점: 기본 개념 미숙, 암기된 내용도 정확하지 않음\n"
            "- 4~5점: 암기는 했으나 적용 경험 없음, 이론만 나열\n"
            "- 6~7점: 개념은 이해했으나 트레이드오프·예외 상황 대처 부족 (불합격)\n"
            "- 8점: 실무 경험 있고 구체적 근거 제시, 단 깊이가 부족\n"
            "- 9점: 원리·트레이드오프·실전 경험 모두 갖춤 (우수)\n"
            "- 10점: 시니어급 답변, 면접관도 배울 점이 있는 수준 (탁월)\n\n"
            "[평가 항목]\n"
            "답변을 아래 두 가지 항목으로 분석하여 각각 1~10점으로 평가하세요:\n\n"
            "1. **기술 이해도 (technical_understanding)**\n"
            "   - 기본 개념, 용어, 원리에 대한 정확한 이해\n"
            "   - 공식 문서 수준의 지식 보유 여부\n"
            "   - 기술 스택의 동작 메커니즘 설명 능력\n\n"
            "2. **문제 해결 능력 (problem_solving)**\n"
            "   - 트레이드오프 분석 및 의사결정 근거 제시\n"
            "   - 실전 장애 대응 및 디버깅 전략\n"
            "   - 확장성·성능·유지보수성 고려 여부\n\n"
            "[피드백 작성 규칙]\n"
            "1. 잘한 점 → 부족한 점 순서로 구체적으로 5문장 이내 작성\n"
            "2. 코드 블록 사용 금지, 함수명·변수명은 자연어 문장 안에 녹여 쓸 것\n"
            "3. 불합격 시 정답을 직접 말하지 말고 생각의 방향만 제시\n"
            "4. 합격 시 한 단계 심화 개념을 짧게 언급하며 격려\n"
            "5. 실무 관점에서 이 답변이 프로덕션 환경에서 어떤 문제를 일으킬 수 있는지 언급"
        )),
        HumanMessage(content=(
            f"[면접 질문]\n{current_question}\n\n"
            f"[지원자 답변]\n{user_answer}\n\n"
            "정밀 채점 결과(점수, 통과여부, 피드백)를 반환해 주세요."
        )),
    ]

    try:
        response = structured_llm.invoke(messages)
        evaluation = {
            "score": response.score,
            "passed": response.passed,
            "reason": response.reason,
            "technical_understanding": response.technical_understanding,
            "problem_solving": response.problem_solving,
        }
    except Exception as e:
        evaluation = {
            "score": 5,
            "passed": False,
            "reason": f"채점 중 오류가 발생했습니다. ({e})",
            "technical_understanding": 5,
            "problem_solving": 5,
        }

    # 3-Strike 아웃 판정
    if evaluation["passed"]:
        # 🔴 5번째 질문이면서 합격한 경우 → 피드백 후 바로 리포트
        if loop_count == 5:  # 🔴 수정: >= 대신 ==
            next_step = "FINAL_REPORT"
            evaluation["reason"] = (
                f"✅ **{evaluation['score']}점으로 합격하셨습니다!**\n\n"
                + evaluation["reason"] + 
                "\n\n면접이 완료되었습니다. 종합 평가를 확인해보세요."
            )
        else:
            next_step = "PASS"
        new_retry = 0
    else:
        new_retry = retry_count + 1
        if new_retry >= 3:
            # 🔴 3번째 실패 시 정답 제공 후 다음 질문으로
            next_step = "ANSWER_REQUEST"
            evaluation["reason"] = (
                "❌ **3번 모두 틀리셨습니다.**\n\n"
                "이 질문은 불합격 처리되며, 모범 답안을 보여드린 후 다음 질문으로 넘어갑니다.\n\n"
                + evaluation["reason"]
            )
        else:
            # 🔴 5번째 질문이면서 불합격한 경우 → 피드백 후 바로 리포트
            if loop_count == 5:  # 🔴 수정: >= 대신 ==
                next_step = "FINAL_REPORT"
                evaluation["reason"] = (
                    f"❌ **{evaluation['score']}점으로 불합격하셨습니다.**\n\n"
                    + evaluation["reason"] + 
                    "\n\n면접이 완료되었습니다. 종합 평가를 확인해보세요."
                )
            else:
                next_step = "HINT"

    return {"evaluation": evaluation, "next_step": next_step, "retry_count": new_retry}
