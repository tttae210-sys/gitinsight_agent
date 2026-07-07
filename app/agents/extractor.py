from app.state import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm

def extract_interview_question(state: InterviewState) -> dict:
    llm = get_llm()
    
    tech_stack = ", ".join(state.get("tech_stack", [])) if state.get("tech_stack") else "알 수 없음"
    loop_count = state.get("loop_count", 0)
    
    system_msg = (
        f"넌 컴퓨터공학과 후배를 위한 친절하고 날카로운 기술 면접관 선배야.\n"
        f"지원자의 기술 스택({tech_stack})과 소스코드 문맥을 보고 면접 질문을 하나 내줘.\n"
        f"현재 꼬리질문 횟수: {loop_count}회차 (최대 3회)\n"
        f"어려운 개념은 이해하기 쉽게 풀어서 설명해주고, 한 번에 하나씩만 물어봐."
    )
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", "이전 답변 히스토리: {history}. 맥락을 이어서 다음 질문이나 꼬리 질문을 던져줘.")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"history": state.get("answer_history", [])})
    
    return {
        "current_question": response.content,
        "loop_count": loop_count + 1
    }