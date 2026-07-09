from typing import Dict, Any, List
from pydantic import BaseModel, Field
from app.schemas import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm


# ==========================================
# 0. LLM 구조적 출력을 위한 Pydantic 스키마 정의
# ==========================================
class EvaluationSchema(BaseModel):
    score: int = Field(
        description="지원자의 답변에 대한 공정한 점수 (1점부터 10점까지)"
    )
    passed: bool = Field(
        description="이전 질문의 핵심 요구사항 및 기술적 논리를 충족했는지 여부. 단순히 '모르겠다', '힌트를 달라', '패스'라고 한 경우는 무조건 False여야 합니다."
    )
    reason: str = Field(
        description="지원자에게 제공할 상세한 기술 피드백. 강점, 보완할 점, 혹은 오답 시 논리적 힌트의 방향성을 시니어 개발자 선배로서 조언하듯 작성합니다."
    )


# ==========================================
# 1. 채점 노드(evaluate_answer) 구현
# ==========================================
def evaluate_answer(state: InterviewState) -> dict:
    """
    지원자의 답변을 프로젝트 소스코드 맥락과 대조하여 정밀 평가합니다.
    [치명적 버그 해결]: 유저가 답변을 포기하거나 힌트를 요청하는 경우,
    LLM을 타지 않고 Python 레이어에서 100% 결정론적으로 오답(Passed=False, Score=1) 처리하여 환각을 차단합니다.
    """
    tech_stack = ", ".join(state.get("tech_stack", []))
    current_question = state.get("current_question", "이전 질문이 존재하지 않습니다.")
    answer_history = state.get("answer_history", [])
    user_answer = answer_history[-1].strip() if answer_history else "답변이 제출되지 않았습니다."
    retry_count = state.get("retry_count", 0)
    chunks = state.get("extracted_chunks", [])

    # 🔴 [치명적 버그 해결 핵심] 포기 발언은 LLM 채점 완전 우회 → 100% 오답 처리
    surrender_keywords = ["모르겠", "모릅니다", "몰라요", "힌트", "패스", "pass", "답이 뭐", "도와줘", "어렵다", "어려워"]
    is_surrender = any(kw in user_answer for kw in surrender_keywords) or len(user_answer) < 5

    if is_surrender:
        evaluation_result = {
            "score": 1,
            "passed": False,
            "reason": (
                "지원자님이 구체적인 기술 설명을 모르겠다고 답변하셨거나 답변의 분량이 부족하여 오답 처리되었습니다. "
                "시니어 면접관 선배로서 지원자님이 스스로 정답의 논리에 닿으실 수 있도록, "
                "작성하신 코드 파일 내에 힌트가 되는 영역을 골라 노란색 형광펜 지목 및 단계별 가이드를 드리겠습니다."
            )
        }
    else:
        llm = get_llm(temperature=0.0)
        structured_llm = llm.with_structured_output(EvaluationSchema)

        code_context = ""
        for chunk in chunks:
            code_context += f"--- File: {chunk.get('file_path')} ---\n{chunk.get('content', chunk.get('code', ''))}\n\n"
        if not code_context:
            code_context = "분석 대상 주요 소스코드가 없습니다."

        system_msg = (
            "당신은 컴퓨터공학과 학생들을 위해 기술 면접을 진행하는 IT 대기업의 매우 정교하고 날카로운 시니어 면접관 선배입니다.\n"
            f"지원자의 기술 스택({tech_stack})과 그들이 직접 작성한 아래 [프로젝트 소스코드 맥락]을 참고하여, "
            "당신이 던진 질문에 대해 지원자가 기술적으로 올바르고 성실한 답변을 제출했는지 채점해야 합니다.\n\n"
            "[프로젝트 소스코드 맥락]\n"
            "{code_context}\n\n"
            "채점 기준:\n"
            "1. 질문에서 물어본 핵심 동작 원리나 아키텍처적 이유를 올바르게 짚었는지 분석하세요.\n"
            "2. 답변이 부실하거나, '잘 모르겠다', '힌트를 주세요' 등 포기성 발언이 섞여 있다면 가차 없이 passed=False로 판정하고 낮은 점수(1~3점)를 부여하세요.\n"
            "3. 만약 완벽한 정답은 아니지만 방향성이 유효하고 기술적 근거가 일부 존재한다면, passed=False로 판정하되 격려 섞인 조언과 함께 score를 4~6점 범위에서 책정하세요.\n"
            "4. 아키텍처 트레이드오프나 동작 논리를 완벽히 방어했다면 passed=True 및 고득점(8~10점)을 부여하세요.\n"
            "5. 피드백 메시지(reason)는 부드럽고 친절하되, 전문적인 기술 용어(CS 지식)를 짚어주며 지적 호기심을 자극하도록 조언체로 작성해 주세요."
        )

        prompt = ChatPromptTemplate.from_messages([
            ("system", system_msg),
            ("human", (
                "[면접관이 던진 질문]\n{current_question}\n\n"
                "[지원자가 제출한 답변]\n{user_answer}\n\n"
                "이 답변에 대해 심사위원으로서 정밀한 채점 결과(점수, 통과여부, 조언)를 반환해 주세요."
            ))
        ])

        chain = prompt | structured_llm

        try:
            response = chain.invoke({
                "code_context": code_context,
                "current_question": current_question,
                "user_answer": user_answer
            })
            evaluation_result = {
                "score": response.score,
                "passed": response.passed,
                "reason": response.reason
            }
        except Exception as e:
            evaluation_result = {
                "score": 5,
                "passed": False,
                "reason": f"평가 모델 연산 도중 예외가 발생했습니다. (오류: {str(e)})"
            }

    # 🔴 [핵심 야구 3-Strike 아웃] 상태 변이 엔진
    is_passed = evaluation_result.get("passed", False)

    if is_passed:
        next_step = "PASS"
        new_retry_count = 0
    else:
        new_retry_count = retry_count + 1
        next_step = "HINT" if new_retry_count < 3 else "FAIL"

    return {
        "evaluation": evaluation_result,
        "next_step": next_step,
        "retry_count": new_retry_count
    }


# ==========================================
# 2. 기존 피드백 리포트 생성 함수 (하위 호환)
# ==========================================
def generate_feedback_report(state: InterviewState) -> dict:
    """전체 면접 질문과 답변 히스토리를 종합하여 리포트를 생성합니다."""
    llm = get_llm(temperature=0.2)

    answer_history = state.get("answer_history", [])
    history_str = ""
    for idx, chat in enumerate(answer_history):
        history_str += f"[{idx+1}회차 대화]: {chat}\n"

    system_msg = (
        "당신은 기술 면접 결과를 종합 분석하여 후배에게 피드백 리포트를 작성해 주는 최고의 테크 리드(Tech Lead)이자 컴퓨터공학과 교수입니다.\n"
        "지원자가 진행한 면접 대화 내용을 보고 전공자가 성장할 수 있는 깊이 있는 리포트를 작성해 주세요.\n\n"
        "출력 포맷 지침:\n"
        "1. **종합 점수 및 평가**: 전공 역량 점수를 마크다운 표(Table) 형태로 요약해 주세요.\n"
        "2. **잘한 점과 부족한 점**: 우수했던 부분과 개념 설명이 부족했던 부분을 명확하게 짚어주세요.\n"
        "3. **소스코드 리팩토링 제안**: 성능 개선이 필요한 부분을 찾아 개선된 Python 예시 코드블록을 포함하여 제안해 주세요.\n"
        "4. **쉽고 명확한 설명**: 어려운 컴퓨터공학 이론을 후배가 완벽하게 이해할 수 있도록 친절하게 설명해 주세요."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", f"전체 면접 질문 및 답변 기록:\n{history_str}\n\n위 기록을 바탕으로 완벽한 종합 피드백 리포트를 작성해 주세요.")
    ])

    chain = prompt | llm
    response = chain.invoke({})
    return {"final_report": response.content}


# ==========================================
# 3. 최종 리포트 생성 노드(generate_final_report) 구현
# ==========================================
def generate_final_report(state: InterviewState) -> dict:
    """
    면접이 최종 종료되었을 때 (성공적 완료 혹은 3-Strike 아웃),
    전체 답변 히스토리와 소스코드 문맥을 종합 분석하여 맞춤형 피드백 리포트를 생성합니다.
    """
    llm = get_llm(temperature=0.3)

    tech_stack = ", ".join(state.get("tech_stack", []))
    answer_history = state.get("answer_history", [])
    chunks = state.get("extracted_chunks", [])
    next_step = state.get("next_step", "FAIL")

    history_conversation = ""
    for idx, chat in enumerate(answer_history):
        role = "지원자(유저)" if idx % 2 != 0 else "면접관(AI)"
        history_conversation += f"- {role}: {chat}\n"

    code_context = ""
    for chunk in chunks:
        code_context += f"--- File: {chunk.get('file_path')} ---\n{chunk.get('content', chunk.get('code', ''))}\n\n"
    if not code_context:
        code_context = "제출된 소스코드가 존재하지 않습니다."

    result_title = "❌ 면접 중단 (3-Strike 아웃 탈락)" if next_step == "FAIL" else "🎉 면접 최종 완료 (성공 패스)"

    system_msg = (
        "당신은 기술 면접을 마치고 지원자에게 최종 성적표를 전달하는 IT 대기업의 매우 따뜻하고 전문적인 시니어 개발자 멘토입니다.\n"
        "지원자가 진행한 모의 면접 기록과 제출한 프로젝트 소스코드를 종합 분석하여, 기술적 성장을 위한 '최종 리팩토링 및 CS 학습 가이드라인 리포트'를 마크다운 형식으로 작성해야 합니다.\n\n"
        "[프로젝트 소스코드 맥락]\n"
        "{code_context}\n\n"
        "지침:\n"
        "1. 리포트는 반드시 깔끔하고 가독성 좋은 GitHub Markdown 스타일로 작성해 주세요.\n"
        "2. 다음 대제목 구조를 완벽하게 갖추어야 합니다:\n"
        "   - ## 📊 면접 종합 평가\n"
        "   - ## 💡 핵심 CS 개념 및 오답 노트\n"
        "   - ## 🛠️ 소스코드 리팩토링 제안 (모범 답안 코드 포함)\n"
        "   - ## 🚀 향후 추천 학습 로드맵\n"
        "3. 아쉽게 탈락했거나 통과한 모든 지원자에게 힘이 되도록 따뜻하고 격려하는 선배의 어조로 작성해 주세요."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", (
            "[최종 면접 상태]: {result_title}\n\n"
            "[실제 진행된 면접 대화록]\n{history_conversation}\n\n"
            "위 정보를 면밀히 복합 분석하여, 지원자만을 위한 세상에 단 하나뿐인 맞춤형 마크다운 피드백 리포트를 생성해 주세요."
        ))
    ])

    chain = prompt | llm

    try:
        response = chain.invoke({
            "code_context": code_context,
            "result_title": result_title,
            "history_conversation": history_conversation
        })
        final_report_md = response.content.strip()
    except Exception as e:
        final_report_md = (
            f"## ⚠️ 리포트 생성 실패\n"
            f"죄송합니다. 평가 리포트를 처리하는 도중 기술적 오류가 발생했습니다. (오류: {str(e)})"
        )

    return {
        "final_report": final_report_md,
        "next_step": "REPORT"
    }
