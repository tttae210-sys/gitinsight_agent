import re
from app.schemas import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm

def classify_user_intent(state: InterviewState) -> dict:
    """유저의 입력을 분석하여 START(시작/링크), ANSWER(면접답변), CHAT(일반대화)으로 분류합니다."""

    user_input = state.get("answer_history", [""])[-1].strip() if state.get("answer_history") else ""
    repo_url = state.get("repo_url", "")

    # 1. 채팅 입력에 깃허브 URL이 직접 포함된 경우 최우선 처리
    github_pattern = r"github\.com/[\w\-]+/[\w\-]+"
    if re.search(github_pattern, user_input):
        urls = re.findall(r'(https?://github\.com/[\w\-]+/[\w\-]+)', user_input)
        extracted_url = urls[0] if urls else user_input
        return {"next_step": "START", "repo_url": extracted_url}

    # 2. 사이드바에서 repo_url이 주입되었고 아직 코드 빌드가 안 된 경우 → START
    #    (extracted_chunks가 비어 있으면 아직 분석 전이라는 의미)
    if repo_url and not state.get("extracted_chunks"):
        return {"next_step": "START", "repo_url": repo_url}

    # 3. 이미 면접 진행 중(질문이 존재)이고 next_step이 ANSWER로 지정된 경우
    if state.get("next_step") == "ANSWER" and state.get("current_question"):
        return {"next_step": "ANSWER"}

    # 4. LLM으로 면접 답변인지 일반 대화인지 분류
    llm = get_llm(temperature=0.0)

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

    if "ANSWER" in intent:
        return {"next_step": "ANSWER"}
    else:
        return {
            "next_step": "CHAT",
            "current_question": (
                "안녕하세요! GitInsight 모의 면접 튜터입니다. "
                "분석할 GitHub Repository URL을 입력해 주시면 코드 기반 기술 면접 질문을 만들어드릴게요."
            ),
        }
