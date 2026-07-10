# app/agents/query_analyzer.py
import re
from pydantic import BaseModel, Field
from typing import Literal, Optional
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from app.schemas import InterviewState
from app.core.config import settings

# LLM이 의도 분석 후 반환할 구조화된 아웃풋 스키마 정의
class IntentAnalysisResult(BaseModel):
    intent: Literal["GREETING", "URL_DETECTED"] = Field(
        description="사용자 입력의 의도 분류. 유효한 GitHub URL이 있으면 URL_DETECTED, 그 외 일반 대화/잡담은 GREETING"
    )
    extracted_url: Optional[str] = Field(
        default=None, description="사용자 입력에서 추출한 깃허브 레포지토리 URL (없는 경우 None)"
    )
    reply_message: Optional[str] = Field(
        default=None, description="GREETING 상태일 때 사용자에 보낼 친절한 스몰토크 및 깃허브 URL 유도 메시지"
    )

async def analyze_node(state: InterviewState) -> dict:
    """
    Agent 0: IntentClassifierAgent
    사용자의 입력 의도를 분석하여 트리거 상태를 결정합니다.
    """
    # 최신 사용자 메시지 가져오기
    user_message = state["messages"][-1].content if state["messages"] else state.get("query", "")
    
    # 1. LLM 초기화 (Config에 등록된 OpenAI 모델 사용)
    llm = ChatOpenAI(model=settings.LLM_MODEL, api_key=settings.OPENAI_API_KEY, temperature=0)
    structured_llm = llm.with_structured_output(IntentAnalysisResult)
    
    # 2. 기획서 페르소나가 반영된 시스템 프롬프트 작성
    prompt = ChatPromptTemplate.from_messages([
        ("system", """당신은 사용자의 입력 의도를 분석하는 영리한 라우터입니다.
        
        [수행 지침]
        1. 입력창에 유효한 깃허브 URL(github.com/유저명/레포명)이 포함되어 있으면 intent를 'URL_DETECTED'로 설정하고 extracted_url에 해당 주소를 추출하세요.
        2. 일반적인 인사, 커리어 관련 잡담, 질문이라면 intent를 'GREETING'으로 설정하세요.
        3. 'GREETING' 상태일 때는 친절하게 스몰토크를 받아주며, 자연스럽게 분석할 프로젝트의 깃허브 주소 제출을 유도하는 응답(reply_message)을 작성하세요.
        
        [GREETING 페르소나 예시]
        "안녕하세요 민우 님! 반가워요. 당연하죠! 제가 민우 님이 작성하신 코드를 아주 송곳처럼 정밀하게 진단해서 실전 면접장처럼 예리하게 훈련시켜 드릴게요. 우선 프로젝트의 '깃허브 레포지토리 주소(URL)'를 알려주세요!"
        """),
        ("human", "{user_input}")
    ])
    
    # 3. 체인 실행 및 분석
    chain = prompt | structured_llm
    analysis: IntentAnalysisResult = await chain.ainvoke({"user_input": user_message})
    
    # 4. 다음 노드로 전달할 State 업데이트 데이터 구성
    update_data = {
        "status": analysis.intent,
        "github_url": analysis.extracted_url if analysis.intent == "URL_DETECTED" else state.get("github_url")
    }
    
    # 만약 잡담(GREETING)인 경우 LLM이 생성한 안내 메시지를 결과에 추가
    if analysis.intent == "GREETING" and analysis.reply_message:
        from langchain_core.messages import AIMessage
        update_data["messages"] = [AIMessage(content=analysis.reply_message)]
        
    return update_data

# 💡 [하위 호환성 추가] 옛날에 작성된 노드 호출 코드가 터지지 않도록 새 함수와 매핑합니다.
intent_classifier_node = analyze_node