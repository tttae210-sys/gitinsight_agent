from app.schemas import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm

def generate_feedback_report(state: InterviewState) -> dict:
    """전체 면접 질문과 답변 히스토리를 종합하여 점수, 장단점 분석, 리팩토링 제안이 담긴 리포트를 생성합니다."""
    llm = get_llm(temperature=0.2)
    
    answer_history = state.get("answer_history", [])
    
    # 질문과 답변을 매칭해서 텍스트로 정렬
    history_str = ""
    for idx, chat in enumerate(answer_history):
        history_str += f"[{idx+1}회차 대화]: {chat}\n"

    system_msg = (
        "당신은 기술 면접 결과를 종합 분석하여 후배에게 피드백 리포트를 작성해 주는 최고의 테크 리드(Tech Lead)이자 컴퓨터공학과 교수입니다.\n"
        "지원자가 진행한 면접 대화 내용을 보고 전공자가 성장할 수 있는 깊이 있는 리포트를 작성해 주세요.\n\n"
        "출력 포맷 지침:\n"
        "1. **종합 점수 및 평가**: 전공 역량 점수를 한눈에 보기 좋게 마크다운 표(Table) 형태로 요약해 주세요. (예: 이해도, 논리성, 코드 활용력 등)\n"
        "2. **잘한 점과 부족한 점**: 답변 내용 중 전공 지식 면에서 우수했던 부분과, 반대로 개념 설명이나 논리가 부족했던 부분을 명확하게 짚어주세요.\n"
        "3. **소스코드 리팩토링 제안**: 유저가 제출했던 소스코드나 답변한 로직 중에서, 성능 개선(시간복잡도 단축, 가독성 향상, 예외처리 추가 등)이 필요한 부분을 찾아 '실제 개선된 Python 예시 코드블록(```python ... ```)'을 포함하여 자세히 제안해 주세요.\n"
        "4. **쉽고 명확한 설명**: 어려운 컴퓨터공학 이론이 있다면 후배가 완벽하게 이해할 수 있도록 친절하고 쉽게 풀어서 설명해 주세요."
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", f"전체 면접 질문 및 답변 기록:\n{history_str}\n\n위 기록을 바탕으로 완벽한 종합 피드백 리포트를 작성해 주세요.")
    ])
    
    chain = prompt | llm
    response = chain.invoke({})
    
    return {"final_report": response.content}