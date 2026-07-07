from app.state import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm

def classify_user_intent(state: InterviewState) -> dict:
    llm = get_llm()
    
    prompt = ChatPromptTemplate.from_messages([
        ("system", "넌 유저의 입력 의도를 분류하는 AI 라우터야. 유저 입력이 '면접 시작'이나 '깃허브 링크'면 'START', 면접 질문에 대한 '답변'이면 'ANSWER', 그냥 일상 대화면 'CHAT'으로 딱 한 단어만 대답해."),
        ("human", "{user_input}")
    ])
    
    user_input = state["answer_history"][-1] if state.get("answer_history") else ""
    
    chain = prompt | llm
    response = chain.invoke({"user_input": user_input})
    
    return {"current_question": response.content.strip()}