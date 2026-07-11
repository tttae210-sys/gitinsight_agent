"""
실시간 인터랙션 에이전트: ReporterAgent
=========================================
역할: 면접이 종료되었을 때 최종 피드백 리포트를 생성하는 단일 책임 노드.
"""

from langchain_core.messages import SystemMessage, HumanMessage
from app.schemas import InterviewState
from app.core.llm import get_llm


def generate_final_report(state: InterviewState) -> dict:
    """[실시간 에이전트] 최종 리포트 생성 전담 노드"""
    llm = get_llm(temperature=0.3)

    tech_stack     = ", ".join(state.get("tech_stack", []))
    answer_history = state.get("answer_history", [])
    chunks         = state.get("extracted_chunks", [])
    next_step      = state.get("next_step", "FAIL")

    history_str = ""
    for idx, chat in enumerate(answer_history):
        role = "지원자(유저)" if idx % 2 != 0 else "면접관(AI)"
        history_str += f"- {role}: {chat}\n"
    history_str = history_str or "(면접 대화 기록이 없습니다.)"

    code_context = ""
    for chunk in chunks:
        code_context += (
            f"--- File: {chunk.get('file_path')} ---\n"
            f"{chunk.get('content', chunk.get('code', ''))}\n\n"
        )
    code_context = code_context or "제출된 소스코드가 존재하지 않습니다."

    result_title = "❌ 면접 중단 (3-Strike 아웃 탈락)" if next_step == "FAIL" else "🎉 면접 최종 완료"

    # SystemMessage/HumanMessage 직접 사용 — ChatPromptTemplate 파싱 완전 우회
    messages = [
        SystemMessage(content=(
            "당신은 FAANG 출신의 시니어 개발자이자 1000명 이상을 코칭한 커리어 멘토입니다. "
            "지원자의 모의 면접 기록과 제출 소스코드를 종합 분석하여 "
            "구체적이고 실용적인 최종 피드백 리포트를 GitHub Markdown 형식으로 작성하세요.\n\n"
            f"[면접 결과]\n{result_title}\n\n"
            f"[지원자 기술 스택]\n{tech_stack or '정보 없음'}\n\n"
            f"[프로젝트 소스코드 맥락]\n{code_context}\n\n"
            "[절대 규칙 - 환각 금지]\n"
            "1. 리포트의 모든 파일명·함수명·코드 인용은 위 소스코드 맥락에 실제로 존재해야 합니다.\n"
            "2. 면접 대화록에 없는 내용을 지원자가 말했다고 임의로 추가하지 마세요.\n"
            "3. 소스코드가 부족하면 그 사실을 솔직히 언급하고 일반 CS 학습 가이드 위주로 작성하세요.\n\n"
            "[리포트 구조 - 반드시 아래 섹션을 완벽히 포함]\n\n"
            "## 📊 면접 종합 평가\n"
            "- 총 질문 수 5개, 합격/불합격 개수, 평균 점수를 마크다운 표로 요약\n"
            "- 평가 항목은 반드시 '기술 이해도'와 '문제 해결 능력' 두 가지만 사용\n"
            "- 최종 판정: 합격(7.0 이상) | 불합격(7.0 미만)\n"
            "- 한 줄 총평 (냉정하지만 격려적으로)\n\n"
            "## 💡 강점 (Keep Doing)\n"
            "- 면접 중 잘했던 점 2~3가지 (구체적 근거와 함께)\n"
            "- 예: '기본 문법 숙지', '솔직한 태도'\n\n"
            "## ⚠️ 약점 (Must Improve)\n"
            "- 면접 중 부족했던 점 2~3가지 (구체적 개선 방향과 함께)\n"
            "- 예: '예외 처리 부재 → try-except, custom exception 학습'\n"
            "- 예: '트레이드오프 이해 부족 → 공식 문서 깊이 읽기'\n"
            "- 예: '이력서 과장 → Redis 기본 개념 학습 후 이력서 수정'\n\n"
            "## 🛠️ 약점 보완 방안\n"
            "- 위 약점에서 언급된 각 항목별로 구체적인 개선 실천 방안을 단계별로 제시\n"
            "- 단계 1~4로 나눠서 구체적 학습 주제와 실습 과제 제시\n"
            "- 각 단계마다 체크리스트 형태로 작성 (- [ ] 항목명)\n"
            "- 예: 단계 1: 예외 처리 마스터 → Python Exception Hierarchy 학습, custom exception 설계 실습\n\n"
            "## 💬 면접관 한마디\n"
            "- 지원자에게 전하는 마지막 격려 메시지 (2~3문장)\n"
            "- 냉정하지만 따뜻한 어조로 작성\n\n"
            "[작성 원칙]\n"
            "- 탈락이든 통과든 모든 지원자에게 힘이 되는 피드백\n"
            "- 구체적 개선 방향 제시 (추상적 격려 금지)\n"
            "- 학습 로드맵은 실천 가능한 수준으로 현실적으로 작성"
        )),
        HumanMessage(content=(
            f"[전체 면접 대화 기록]\n{history_str}\n\n"
            "위 기록을 바탕으로 완벽한 종합 피드백 리포트를 작성해 주세요."
        )),
    ]

    try:
        response       = llm.invoke(messages)
        report_content = response.content
    except Exception as e:
        report_content = f"## 리포트 생성 실패\n피드백 리포트 처리 중 오류가 발생했습니다. (오류: {e})"

    return {"final_report": report_content}
