# app/core/config.py
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Optional

class Settings(BaseSettings):
    # 1. 프로젝트 기본 정보
    PROJECT_NAME: str = "GitInsight Agent"
    VERSION: str = "1.0.0"
    
    # 2. API Keys 및 LLM 설정 (OpenAI와 Upstage Solar를 모두 유연하게 지원)
    OPENAI_API_KEY: Optional[str] = None
    UPSTAGE_API_KEY: str  # 필수 값으로 지정 (없으면 서버 시작 시 에러 발생시켜 방어)
    LLM_MODEL: str = "gpt-3.5-turbo"
    
    # 3. Vector DB 로컬 경로
    CHROMA_DB_DIR: str = "./chroma_db"
    
    # 4. [아키텍트님 기획 반영] 에이전트 튜터링 루프 및 Rerank 가드레일 핵심 규칙
    MAX_LOOP_COUNT: int = 3        # 최대 3회 차 제한 튜터링 루프
    RERANK_THRESHOLD: int = 7      # 7점 미만 노이즈 필터링 임계값

    # Pydantic Settings가 자동으로 최상위 .env 파일을 찾아 읽어옵니다.
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore"
    )

# 팀원들이 전역에서 'from app.core.config import settings'로 사용할 인스턴스
settings = Settings()

# 💡 [하위 호환성 추가] 옛날에 작성된 Config 호출 코드가 터지지 않도록 매핑합니다.
Config = settings
# 💡 [CORS 에러 방어] main.py에서 CORS 설정을 정상적으로 가져갈 수 있도록 상수를 추가합니다.
CORS_ORIGINS = ["*"]
# 💡 [데이터베이스 에러 방어] database.py에서 요구하는 크로마 DB 설정을 기본값으로 추가합니다.
CHROMA_MODE: str = "local"
CHROMA_HOST: str = "localhost"
CHROMA_PORT: int = 8000