from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Literal
from typing_extensions import TypedDict, Annotated
import operator

# ==========================================
# 1. LangGraph State (팀원이 작성한 최신 상태 관리)
# ==========================================
class InterviewState(TypedDict):
    user_id: str
    repo_url: str
    repo_commit_hash: str
    tech_stack: List[str]
    extracted_chunks: Annotated[List[Dict], operator.add]
    current_question: str
    answer_history: Annotated[List[str], operator.add]
    loop_count: int
    evaluation: Optional[Dict]
    final_report: Optional[str]
    next_step: str


# ==========================================
# 2. FastAPI Chat API 스키마 (누락되어 에러가 났던 부분 복구)
# ==========================================
class ChatRequest(BaseModel):
    query: str
    message: Optional[str] = None
    repo_url: Optional[str] = None
    user_id: str = "default_user"
    current_question: str = ""
    current_retry_count: int = Field(default=0, ge=0, le=3)
    answer_history: List[str] = Field(default_factory=list)

class ChatResponseData(BaseModel):
    evaluation_score: int = 0
    feedback: str = ""
    is_finished: bool = False
    next_question: str = ""
    answer: str = ""
    status: Literal["QUESTION", "HINT", "PASS", "FAIL", "CHAT", "REPORT"] = "QUESTION"
    new_retry_count: int = 0
    tech_stack: List[str] = Field(default_factory=list)
    extracted_chunks: List[Dict] = Field(default_factory=list)
    final_report: str = ""

class ChatResponse(BaseModel):
    status: str = "success"
    data: ChatResponseData

class StreamEvent(BaseModel):
    event: str
    node: Optional[str] = None
    data: str = ""


# ==========================================
# 3. RAG API 스키마 (당신이 만든 DB 연동 모듈용)
# ==========================================
class SearchRequest(BaseModel):
    question: str
    n_results: int = Field(default=3, ge=1, le=20)
    repo_url: Optional[str] = None
    commit_hash: Optional[str] = None

class SearchResultItem(BaseModel):
    content: str
    metadata: dict = {}
    distance: Optional[float] = None

class SearchResponse(BaseModel):
    results: list[SearchResultItem]
    total: int
