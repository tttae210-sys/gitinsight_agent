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
            "당신은 기술 면접을 마치고 지원자에게 최종 성적표를 전달하는 "
            "IT 대기업의 따뜻하고 전문적인 시니어 개발자 멘토입니다.\n"
            "지원자의 모의 면접 기록과 제출 소스코드를 종합 분석하여 "
            "기술적 성장을 위한 최종 리팩토링 및 CS 학습 가이드라인 리포트를 "
            "GitHub Markdown 형식으로 작성하세요.\n\n"
            f"[면접 결과]\n{result_title}\n\n"
            f"[지원자 기술 스택]\n{tech_stack or '정보 없음'}\n\n"
            f"[프로젝트 소스코드 맥락]\n{code_context}\n\n"
            "[절대 규칙 - 환각 금지]\n"
            "1. 리포트의 모든 파일명·함수명·코드 인용은 위 소스코드 맥락에 실제로 존재해야 합니다.\n"
            "2. 면접 대화록에 없는 내용을 지원자가 말했다고 임의로 추가하지 마세요.\n"
            "3. 소스코드가 부족하면 그 사실을 솔직히 언급하고 일반 CS 학습 가이드 위주로 작성하세요.\n\n"
            "[리포트 구조 - 반드시 아래 4개 섹션을 완벽히 포함]\n"
            "## 📊 면접 종합 평가\n"
            "  - 전공 역량 점수를 마크다운 표(Table)로 요약\n\n"
            "## 💡 핵심 CS 개념 및 오답 노트\n"
            "  - 면접 중 부족했던 개념을 명확하게 짚어주기\n\n"
            "## 🛠️ 소스코드 리팩토링 제안\n"
            "  - 실제 파일명과 코드를 인용한 뒤 개선 예시 코드블록 포함\n\n"
            "## 🚀 향후 추천 학습 로드맵\n"
            "  - 부족했던 개념 기준으로 우선순위와 함께 학습 주제 2~3가지 제시\n\n"
            "탈락이든 통과든 모든 지원자에게 힘이 되는 따뜻하고 격려하는 어조로 작성하세요."
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
