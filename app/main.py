from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import router
from app.core.config import CORS_ORIGINS
from app.service.vector_service import get_vector_service
from app.core.seed import SeedManager

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 1. VectorService 싱글턴 초기화 (ChromaDB 컬렉션 생성 포함)
    vector_service = get_vector_service()

    # 2. FastAPI 앱 상태에 저장 → 라우터/의존성에서 request.app.state.vector_service 로 접근 가능
    app.state.vector_service = vector_service

    # 3. SeedManager에 vector_service를 주입하고, 비어 있을 때만 초기 데이터 적재
    SeedManager(vector_service).run_if_empty()

    yield

app = FastAPI(title="GitInsight Agent API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api/v1", tags=["chat"])

@app.get("/health")
def health(): 
    return {"status": "healthy"}
