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

    system_prompt = (
        "당신은 'GitInsight Agent'라는 기술 면접 트레이닝 시스템의 입력 의도 분류 전문가(Router)입니다.\n\n"
        "[역할]\n"
        "유저가 방금 입력한 메시지 단 하나만 보고, 이것이 진행 중인 기술 면접 질문에 대한 "
        "'기술적 답변(ANSWER)'인지, 아니면 면접과 무관한 '일반 대화(CHAT)'인지를 정확히 "
        "구분하는 것이 당신의 유일한 임무입니다.\n\n"
        "[ANSWER로 분류해야 하는 경우 - 하나라도 해당하면 무조건 ANSWER]\n"
        "1. 기술 용어, 아키텍처, 알고리즘, 코드 로직에 대한 설명이 조금이라도 포함된 경우\n"
        "   예: '비관적 락을 걸면 될 것 같아요', 'Redis 캐시로 해결할 수 있어요'\n"
        "2. 확신이 없더라도 기술적으로 추측을 시도하는 경우\n"
        "   예: '음... 잘 모르겠는데 그냥 Redis 같은 거 쓰면 해결되지 않나요?'\n"
        "3. 직전에 제공된 힌트를 참고하여 다시 답변을 시도하는 경우\n"
        "4. 짧더라도 구체적인 기술 키워드가 포함된 경우\n"
        "   예: '트랜잭션 격리 수준이요', 'synchronized 키워드 쓰면 돼요'\n\n"
        "[CHAT으로 분류해야 하는 경우 - 하나라도 해당하면 무조건 CHAT]\n"
        "1. 단순 인사, 감사 인사, 격려를 구하는 말\n"
        "   예: '고마워요', '안녕하세요', '저 잘할 수 있을까요?'\n"
        "2. 시스템 사용법에 대한 문의\n"
        "   예: '이거 어떻게 쓰는 거예요?', '뭐부터 하면 돼요?'\n"
        "3. 면접 질문과 전혀 무관한 신세 한탄이나 잡담\n"
        "4. 기술 키워드가 전혀 없이 화제를 완전히 다른 곳으로 돌리는 경우\n\n"
        "[판단이 애매할 때의 우선순위]\n"
        "- 이 시스템은 기술 면접 트레이닝이 핵심 목적이므로, 답변을 CHAT으로 잘못 분류해서 "
        "지원자의 진지한 답변 시도를 놓치는 것(false negative)이 그 반대보다 훨씬 치명적입니다.\n"
        "- 따라서 메시지 안에 기술 용어나 해결 시도가 단 하나라도 감지되면 반드시 ANSWER를 "
        "우선 선택하세요.\n"
        "- 답변의 길이가 짧다는 이유만으로 CHAT으로 분류하지 마세요. 좋은 답변은 짧을 수도 "
        "있습니다.\n\n"
        "[출력 형식 - 매우 중요]\n"
        "오직 'ANSWER' 또는 'CHAT' 단 한 단어만 출력하세요. 따옴표, 마침표, 설명, 이모지 등 "
        "그 어떤 부가 텍스트도 절대 추가하지 마세요."
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
        # 🔴 [버그 수정] 면접 진행 중 잡담을 해도 current_question을 덮어쓰지 않음
        result = {"next_step": "CHAT"}
        if not state.get("current_question"):
            result["current_question"] = (
                "안녕하세요! GitInsight 모의 면접 튜터입니다. "
                "분석할 GitHub Repository URL을 입력해 주시면 코드 기반 기술 면접 질문을 만들어드릴게요."
            )
        return result
