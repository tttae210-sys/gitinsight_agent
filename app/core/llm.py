import os
import time
from langchain_core.language_models.chat_models import BaseChatModel
from langchain_upstage import ChatUpstage
from langchain_openai import ChatOpenAI

# 강의 노트북과 동일한 모델명 사용
SOLAR_MODEL = "solar-pro2"
OPENAI_MODEL = "gpt-4o-mini"  # 또는 "gpt-4o"


def get_llm(temperature: float = 0.0, model: str | None = None) -> BaseChatModel:
    """
    LLM 클라이언트를 생성합니다.
    
    우선순위:
    1. OPENAI_API_KEY가 있으면 OpenAI 사용 (Rate Limit 여유)
    2. 없으면 UPSTAGE_API_KEY 사용
    """
    openai_key = os.getenv("OPENAI_API_KEY")
    
    if openai_key:
        return ChatOpenAI(
            model=model or OPENAI_MODEL,
            temperature=temperature,
            api_key=openai_key,
            max_retries=3,  # 자동 재시도
        )
    else:
        return ChatUpstage(
            model=model or SOLAR_MODEL,
            temperature=temperature,
            max_retries=3,  # Rate Limit 시 자동 재시도
        )
