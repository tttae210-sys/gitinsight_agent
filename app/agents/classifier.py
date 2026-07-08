import re
from app.schemas import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm

def classify_user_intent(state: InterviewState) -> dict:
    """유저의 입력을 분석하여 START(시작/링크), ANSWER(면접답변), CHAT(일반대화)으로 분류합니다."""
    llm = get_llm(temperature=0.0)
    
    # 최근 유저 입력 가져오기
    user_input = state["answer_history"][-1] if state.get("answer_history") else ""
    user_input = user_input.strip()
    
    # 1. 정규표현식으로 깃허브 레포지토리 링크가 포함되어 있는지 최우선 검사
    github_pattern = r"github\.com/[\w\-]+/[\w\-]+"
    if re.search(github_pattern, user_input):
        # 입력에서 URL만 추출해서 저장하기 위해 함께 반환
        urls = re.findall(r'(https?://github\.com/[\w\-]+/[\w\-]+)', user_input)
        repo_url = urls[0] if urls else user_input
        return {"next_step": "START", "repo_url": repo_url}
    
    # 2. 링크가 없다면 LLM을 통해 면접 답변인지 일반 대화인지 분류
    prompt = ChatPromptTemplate.from_messages([
        ("system", (
            "당신은 기술 면접 시스템의 정교한 라우터입니다. 유저의 입력이 앞선 면접 질문에 대한 '답변'이거나 "
            "기술적인 설명이 포함되어 있다면 오직 'ANSWER'라고만 대답하세요. "
            "반면, 질문이 아닌 단순 인사, 시스템 사용법 문의, 혹은 일상적인 대화라면 오직 'CHAT'이라고만 대답하세요.\n"
            "단 한 단어(ANSWER 또는 CHAT) 외에는 아무것도 출력하지 마세요."
        )),
        ("human", "유저 입력: {user_input}")
    ])
    
    chain = prompt | llm
    response = chain.invoke({"user_input": user_input})
    intent = response.content.strip().upper()
    
    # 방어 코드: 엉뚱한 문자열이 올 경우를 대비
    if "ANSWER" in intent:
        return {"next_step": "ANSWER"}
    else:
        return {"next_step": "CHAT"}