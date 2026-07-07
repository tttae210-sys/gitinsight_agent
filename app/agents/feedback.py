from app.state import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm

def generate_feedback_report(state: InterviewState) -> dict:
    llm = get_llm()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "넌 기술 면접 결과를 분석해서 친절한 피드백이랑 코드 리팩토링 제안을 해주는 시니어 개발자야. 지원자의 답변을 보고 점수, 잘한 점, 아쉬운 점, 개선 방향을 표나 그림을 설명하듯 아주 자세하게 적어줘."),
        ("human", "질문과 나의 답변 히스토리: {history}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"history": state.get("answer_history", [])})
    
    return {"final_report": response.content}