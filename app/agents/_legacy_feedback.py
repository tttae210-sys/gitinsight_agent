from typing import Dict, Any, List
from pydantic import BaseModel, Field
from app.schemas import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm


# ==========================================
# 0. LLM 구조적 출력을 위한 Pydantic 스키마 정의
# ==========================================
class EvaluationSchema(BaseModel):
    score: int = Field(description="지원자의 답변에 대한 공정한 점수 (1점부터 10점까지)")
    passed: bool = Field(
        description="이전 질문의 핵심 요구사항 및 기술적 논리를 충족했는지 여부. "
                    "단순히 '모르겠다', '힌트를 달라', '패스'라고 한 경우는 무조건 False여야 합니다."
    )
    reason: str = Field(
        description="지원자에게 제공할 상세한 기술 피드백. 강점, 보완할 점, 혹은 오답 시 "
                    "논리적 힌트의 방향성을 시니어 개발자 선배로서 조언하듯 작성합니다."
    )


# ==========================================
# 1. 채점 노드(evaluate_answer) 구현
# ==========================================
def evaluate_answer(state: InterviewState) -> dict:
    """
    지원자의 답변을 프로젝트 소스코드 맥락과 대조하여 정밀 평가합니다.
    [버그 수정]: '어렵다', '도와줘' 같은 단어가 포함된 기술적 답변이
    자동 오답 처리되는 문제를 해결. 명확한 포기 문구만 즉시 오답 처리합니다.
    """
    tech_stack = ", ".join(state.get("tech_stack", []))
    current_question = state.get("current_question", "이전 질문이 존재하지 않습니다.")
    answer_history = state.get("answer_history", [])
    user_answer = answer_history[-1].strip() if answer_history else "답변이 제출되지 않았습니다."
    retry_count = state.get("retry_count", 0)
    chunks = state.get("extracted_chunks", [])

    # 🔴 [버그 수정] '어렵다', '도와줘' 같은 약한 신호 단어는 짧은 답변(15자 미만)일 때만 포기로 간주
    strong_giveup_phrases = ["모르겠", "모릅니다", "몰라요", "패스", "pass"]
    hint_request_phrases = ["힌트 주세요", "힌트를 줘", "힌트 줘", "힌트좀", "힌트 좀", "알려줘요"]
    answer_request_phrases = ["정답이 뭐", "답이 뭐", "답을 알려", "정답 알려", "정답을 알려", "답 알려줘", "정답 줘", "정답을 줘", "답 줘", "모범 답안", "답 알려", "정답 알려줘", "답알려줘", "정답알려줘"]
    weak_signal_words = ["어렵다", "어려워", "어려운", "도와줘"]

    has_strong_giveup = any(kw in user_answer for kw in strong_giveup_phrases)
    has_hint_request = any(kw in user_answer for kw in hint_request_phrases)
    has_answer_request = any(kw in user_answer for kw in answer_request_phrases)
    has_weak_signal_only = (
        any(kw in user_answer for kw in weak_signal_words) and len(user_answer) < 15
    )
    is_too_short = len(user_answer) < 5
    is_surrender = has_strong_giveup or has_hint_request or has_weak_signal_only or is_too_short

    # 정답 요청 시 → LLM이 정답을 직접 알려줌
    if has_answer_request:
        llm = get_llm(temperature=0.3)

        code_context = ""
        for chunk in chunks:
            code_context += f"--- File: {chunk.get('file_path')} ---\n{chunk.get('content', chunk.get('code', ''))}\n\n"
        if not code_context:
            code_context = "분석 대상 주요 소스코드가 없습니다."

        answer_prompt = ChatPromptTemplate.from_messages([
            ("system", (
                "당신은 IT 대기업 출신의 친절한 시니어 개발자 멘토입니다.\n"
                "지원자가 면접 질문의 정답을 직접 요청했습니다. 이제 힌트가 아닌 명확하고 완전한 모범 답안을 알려주세요.\n\n"
                "[프로젝트 소스코드 맥락]\n{code_context}\n\n"
                "[작성 지침]\n"
                "1. 질문에 대한 핵심 개념과 원리를 정확하게 설명하세요.\n"
                "2. 지원자의 소스코드를 기반으로 구체적인 예시를 들어 설명하세요.\n"
                "3. 코드 예시가 필요하다면 코드 블록을 사용해도 됩니다.\n"
                "4. 마지막에 이 개념을 공부할 수 있는 핵심 키워드를 1~2개 짧게 제안해 주세요.\n"
                "5. 친절하고 격려하는 선배의 어조로 작성하세요."
            )),
            ("human", (
                "[면접 질문]\n{current_question}\n\n"
                "위 질문에 대한 완전한 모범 답안을 알려주세요."
            ))
        ])

        chain = answer_prompt | llm
        try:
            response = chain.invoke({
                "code_context": code_context,
                "current_question": current_question,
            })
            answer_reason = response.content.strip()
        except Exception as e:
            answer_reason = f"모범 답안 생성 중 오류가 발생했습니다. (오류: {str(e)})"

        evaluation_result = {
            "score": 0,
            "passed": False,
            "reason": f"📖 **모범 답안**\n\n{answer_reason}"
        }
        return {
            "evaluation": evaluation_result,
            "next_step": "ANSWER_GIVEN",
            "retry_count": min(retry_count + 1, 3)
        }

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
            "당신은 컴퓨터공학과 학생들을 대상으로 기술 면접을 진행하는 IT 대기업의 매우 정교하고 "
            "날카로운 시니어 면접관 선배입니다. 당신의 채점 결과는 지원자의 학습 방향에 직접 영향을 "
            "미치므로, 반드시 일관되고 공정한 기준으로 평가해야 합니다.\n\n"
            f"[지원자 기술 스택]\n{tech_stack if tech_stack else '정보 없음'}\n\n"
            "[지원자가 직접 작성한 프로젝트 소스코드 맥락]\n"
            "{code_context}\n\n"
            "[절대 규칙 - 환각(Hallucination) 금지]\n"
            "1. 오직 위에 제공된 [프로젝트 소스코드 맥락]과 지원자의 답변만을 근거로 채점하세요.\n"
            "2. 소스코드 맥락만으로 판단이 부족한 일반적인 CS 지식 질문이라면, "
            "해당 분야의 정확한 이론적 지식을 기준으로 채점하세요.\n\n"
            "[채점 기준 - 세부 루브릭]\n"
            "- 1~3점 (불합격): 질문의 핵심을 전혀 짚지 못했거나, 기술적으로 명백히 틀린 설명을 "
            "했거나, 포기성 발언만 있는 경우\n"
            "- 4~6점 (불합격이지만 방향성은 인정): 완벽한 정답은 아니지만 문제의 본질은 정확히 "
            "인지하고 있고, 최소한의 기술적 근거를 제시한 경우\n"
            "- 7점 (경계선, 원칙적으로 불합격 처리): 핵심 개념은 맞았지만 구체적인 해결 방법이나 "
            "실제 구현 레벨의 디테일이 부족한 경우\n"
            "- 8~10점 (합격): 질문에서 요구한 핵심 동작 원리나 아키텍처적 트레이드오프를 정확하고 "
            "구체적으로 설명했으며, 실제로 구현 가능한 수준의 해결책까지 제시한 경우\n\n"
            "[피드백(reason) 작성 지침]\n"
            "1. 먼저 지원자 답변에서 잘한 점이 있다면 한 문장으로 짚어주세요.\n"
            "2. 이어서 부족한 부분을 구체적인 기술 용어와 함께 명확히 지적하세요.\n"
            "3. 절대로 코드를 그대로 인용하거나 코드 블록(```...```)을 사용하지 마세요. "
            "코드 내용은 자연어로 풀어서 설명하세요. "
            "예시) 'get_connection 함수에서 매번 새로운 커넥션을 여는 부분' 처럼 "
            "함수명·변수명은 문장 안에 자연스럽게 녹여 쓰세요.\n"
            "4. 불합격(passed=False)인 경우, 정답을 직접 알려주지 말고 단계적인 힌트나 관련 "
            "키워드만 제시하세요 (소크라테스식 질문법을 사용하세요).\n"
            "5. 합격(passed=True)인 경우, 정답을 확인해주고 한 단계 더 심화된 개념을 짧게 "
            "언급하며 격려하세요.\n"
            "6. 전체 톤은 친절하고 다정한 선배의 어조를 유지하되, 기술적으로 틀린 부분에 대한 "
            "지적은 절대 타협하지 마세요.\n"
            "7. 전체 피드백은 5문장 이내로 간결하게 작성하세요."
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
        if new_retry_count < 3:
            next_step = "HINT"
        else:
            next_step = "FAIL"
            evaluation_result["reason"] = "❌ **면접 불합격**\n\n" + evaluation_result.get("reason", "")

    return {
        "evaluation": evaluation_result,
        "next_step": next_step,
        "retry_count": new_retry_count
    }


def provide_answer(state: InterviewState) -> dict:
    """
    지원자가 정답을 직접 요청했을 때 모범 답안을 생성합니다.
    힌트가 아닌 완전한 해설을 제공합니다.
    """
    llm = get_llm(temperature=0.3)
    current_question = state.get("current_question", "")
    chunks = state.get("extracted_chunks", [])
    retry_count = state.get("retry_count", 0)

    code_context = ""
    for chunk in chunks:
        code_context += f"--- File: {chunk.get('file_path')} ---\n{chunk.get('content', chunk.get('code', ''))}\n\n"
    if not code_context:
        code_context = "분석 대상 주요 소스코드가 없습니다."

    answer_prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "당신은 IT 대기업 출신의 시니어 개발자 멘토입니다.\n"
            "지원자가 면접 질문의 정답을 직접 요청했습니다. 불필요한 인사말, 칭찬, 감탄사 없이 바로 모범 답안을 제공하세요.\n\n"
            "[프로젝트 소스코드 맥락]\n{code_context}\n\n"
            "[작성 지침]\n"
            "1. '안녕하세요', '멋진 질문이에요', '좋은 질문입니다' 같은 인사나 감탄사로 시작하지 마세요.\n"
            "2. 바로 핵심 개념과 원리 설명으로 시작하세요.\n"
            "3. 지원자의 소스코드를 기반으로 구체적인 예시를 들어 설명하세요.\n"
            "4. 코드 예시가 필요하다면 코드 블록을 사용해도 됩니다.\n"
            "5. 마지막에 이 개념을 공부할 수 있는 핵심 키워드를 1~2개 짧게 제안하세요.\n"
            "6. 전체 내용은 간결하고 핵심만 담아서 작성하세요."
        )),
        ("human", (
            "[면접 질문]\n{current_question}\n\n"
            "위 질문에 대한 완전한 모범 답안을 알려주세요."
        ))
    ])

    chain = answer_prompt | llm
    try:
        response = chain.invoke({
            "code_context": code_context,
            "current_question": current_question,
        })
        answer_text = response.content.strip()
    except Exception as e:
        answer_text = f"모범 답안 생성 중 오류가 발생했습니다. (오류: {str(e)})"

    evaluation_result = {
        "score": 0,
        "passed": False,
        "reason": f"📖 **모범 답안**\n\n{answer_text}"
    }

    return {
        "evaluation": evaluation_result,
        "next_step": "ANSWER_GIVEN",
        "retry_count": min(retry_count + 1, 3)
    }


def generate_feedback_report(state: InterviewState) -> dict:
    """전체 면접 질문과 답변 히스토리를 종합하여 리포트를 생성합니다."""
    llm = get_llm(temperature=0.2)

    answer_history = state.get("answer_history", [])
    history_str = ""
    for idx, chat in enumerate(answer_history):
        history_str += f"[{idx+1}회차 대화]: {chat}\n"
    if not history_str:
        history_str = "(면접 대화 기록이 없습니다.)"

    system_msg = (
        "당신은 기술 면접 결과를 종합 분석하여 후배에게 피드백 리포트를 작성해 주는 최고의 테크 리드(Tech Lead)이자 컴퓨터공학과 교수입니다.\n"
        "지원자가 진행한 면접 대화 내용을 보고 전공자가 성장할 수 있는 깊이 있는 리포트를 작성해 주세요.\n\n"
        "출력 포맷 지침:\n"
        "1. **종합 점수 및 평가**: 전공 역량 점수를 마크다운 표(Table) 형태로 요약해 주세요.\n"
        "2. **잘한 점과 부족한 점**: 우수했던 부분과 개념 설명이 부족했던 부분을 명확하게 짚어주세요.\n"
        "3. **소스코드 리팩토링 제안**: 성능 개선이 필요한 부분을 찾아 개선된 Python 예시 코드블록을 포함하여 제안해 주세요.\n"
        "4. **쉽고 명확한 설명**: 어려운 컴퓨터공학 이론을 후배가 완벽하게 이해할 수 있도록 친절하게 설명해 주세요."
    )

    # 🔴 [버그 수정] f-string 대신 템플릿 변수로 주입 → 답변에 중괄호 포함 시 파싱 오류 방지
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", "전체 면접 질문 및 답변 기록:\n{history_str}\n\n위 기록을 바탕으로 완벽한 종합 피드백 리포트를 작성해 주세요.")
    ])

    chain = prompt | llm
    try:
        response = chain.invoke({"history_str": history_str})
        report_content = response.content
    except Exception as e:
        report_content = f"## ⚠️ 리포트 생성 실패\n피드백 리포트를 처리하는 도중 오류가 발생했습니다. (오류: {str(e)})"

    return {"final_report": report_content}


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
    if not history_conversation:
        history_conversation = "(면접 대화 기록이 없습니다.)"

    code_context = ""
    for chunk in chunks:
        code_context += f"--- File: {chunk.get('file_path')} ---\n{chunk.get('content', chunk.get('code', ''))}\n\n"
    if not code_context:
        code_context = "제출된 소스코드가 존재하지 않습니다."

    result_title = "❌ 면접 중단 (3-Strike 아웃 탈락)" if next_step == "FAIL" else "🎉 면접 최종 완료 (성공 패스)"

    system_msg = (
        "당신은 기술 면접을 마치고 지원자에게 최종 성적표를 전달하는 IT 대기업의 매우 따뜻하고 "
        "전문적인 시니어 개발자 멘토입니다. 지원자가 진행한 모의 면접 기록과 제출한 프로젝트 "
        "소스코드를 종합 분석하여, 기술적 성장을 위한 '최종 리팩토링 및 CS 학습 가이드라인 리포트'를 "
        "마크다운 형식으로 작성해야 합니다.\n\n"
        "[프로젝트 소스코드 맥락]\n"
        "{code_context}\n\n"
        "[절대 규칙 - 환각 금지]\n"
        "1. 리포트에 등장하는 모든 파일명, 함수명, 코드 인용은 반드시 위 [프로젝트 소스코드 맥락]에 "
        "실제로 존재하는 내용이어야 합니다.\n"
        "2. [실제 진행된 면접 대화록]에 없는 내용을 지원자가 말했다고 임의로 추가하지 마세요.\n"
        "3. 소스코드 맥락이 비어 있거나 부족하다면, 그 사실을 솔직히 언급하고 일반적인 CS "
        "학습 가이드 위주로 작성하세요.\n\n"
        "지침:\n"
        "1. 리포트는 반드시 깔끔하고 가독성 좋은 GitHub Markdown 스타일로 작성해 주세요.\n"
        "2. 다음 대제목 구조를 완벽하게 갖추어야 합니다:\n"
        "   - ## 📊 면접 종합 평가\n"
        "   - ## 💡 핵심 CS 개념 및 오답 노트\n"
        "   - ## 🛠️ 소스코드 리팩토링 제안 (모범 답안 코드 포함)\n"
        "   - ## 🚀 향후 추천 학습 로드맵\n"
        "3. '## 🛠️ 소스코드 리팩토링 제안' 섹션에서는 반드시 실제로 존재하는 파일명과 코드를 "
        "인용한 뒤, 개선된 예시 코드를 코드블록으로 제시하세요.\n"
        "4. '## 🚀 향후 추천 학습 로드맵' 섹션에서는 면접 중 부족했던 개념을 기준으로 구체적인 "
        "학습 주제 2~3가지를 우선순위와 함께 제시하세요.\n"
        "5. 아쉽게 탈락했거나 통과한 모든 지원자에게 힘이 되도록 따뜻하고 격려하는 선배의 어조로 "
        "작성해 주세요."
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
