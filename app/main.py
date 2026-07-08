from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api import router
from app.core.config import CORS_ORIGINS
from app.vector_store import seed_if_empty

@asynccontextmanager
async def lifespan(app: FastAPI):
    seed_if_empty()
    yield

# [수정됨] title을 Medical QA에서 GitInsight Agent API로 변경
app = FastAPI(title="GitInsight Agent API", version="1.0.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=CORS_ORIGINS, allow_credentials=True, allow_methods=["*"], allow_headers=["*"])
app.include_router(router, prefix="/api/v1", tags=["chat"])

@app.get("/health")
def health(): 
    return {"status": "healthy"}