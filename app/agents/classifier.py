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
    if repo_url and not state.get("extracted_chunks"):
        return {"next_step": "START", "repo_url": repo_url}

    # 3. 면접이 진행 중이면 (current_question이 존재하면) 무조건 ANSWER로 처리
    #    "모르겠어", "힌트 줘" 같은 포기 발언도 포함 — evaluator가 판단해서 HINT/FAIL 처리
    if state.get("current_question") and state.get("extracted_chunks"):
        return {"next_step": "ANSWER"}

    # 4. LLM으로 면접 답변인지 일반 대화인지 분류 (면접 시작 전 단계)
    llm = get_llm(temperature=0.0)

    system_prompt = (
        "당신은 'GitInsight Agent'라는 기술 면접 트레이닝 시스템의 입력 의도 분류 전문가(Router)입니다.\n\n"
        "[역할]\n"
        "유저가 방금 입력한 메시지 단 하나만 보고, 이것이 진행 중인 기술 면접 질문에 대한 "
        "'기술적 답변(ANSWER)'인지, 아니면 면접과 무관한 '일반 대화(CHAT)'인지를 정확히 "
        "구분하는 것이 당신의 유일한 임무입니다.\n\n"
        "[ANSWER로 분류해야 하는 경우 - 하나라도 해당하면 무조건 ANSWER]\n"
        "1. 기술 용어, 아키텍처, 알고리즘, 코드 로직에 대한 설명이 조금이라도 포함된 경우\n"
        "2. 확신이 없더라도 기술적으로 추측을 시도하는 경우\n"
        "3. 짧더라도 구체적인 기술 키워드가 포함된 경우\n\n"
        "[CHAT으로 분류해야 하는 경우]\n"
        "1. 단순 인사, 감사 인사\n"
        "2. 시스템 사용법에 대한 문의\n"
        "3. 기술 키워드가 전혀 없는 잡담\n\n"
        "[출력 형식 - 매우 중요]\n"
        "오직 'ANSWER' 또는 'CHAT' 단 한 단어만 출력하세요."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_prompt),
        ("human", "유저 입력: {user_input}")
    ])

    chain = prompt | llm
    response = chain.invoke({"user_input": user_input})
    intent = response.content.strip().upper()

    if "ANSWER" in intent:
        return {"next_step": "ANSWER"}
    else:
        result = {"next_step": "CHAT"}
        if not state.get("current_question"):
            result["current_question"] = (
                "안녕하세요! GitInsight 모의 면접 튜터입니다. "
                "분석할 GitHub Repository URL을 입력해 주시면 코드 기반 기술 면접 질문을 만들어드릴게요."
            )
        return result
