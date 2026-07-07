from typing import TypedDict, List, Dict, Optional
from pydantic import BaseModel

# ==========================================
# 1. 기존 프로젝트용 상태 관리 스키마 (LangGraph 등에서 활용)
# ==========================================
class InterviewState(TypedDict):
    user_id: str
    repo_url: str
    repo_commit_hash: str        

    tech_stack: List[str]        
    extracted_chunks: List[Dict] 

    current_question: str        
    answer_history: List[str]    
    loop_count: int              

    evaluation: Optional[Dict]   
    final_report: Optional[str]  


# ==========================================
# 2. FastAPI 통신 및 라우터 매핑용 스키마 (ImportError 해결용)
# ==========================================
class ChatRequest(BaseModel):
    query: str
    message: Optional[str] = None  # 조원분 코드 호환용 추가
    repo_url: Optional[str] = None
    user_id: Optional[str] = "default_user"

class ChatResponse(BaseModel):
    answer: str
    status: Optional[str] = "success"

class StreamEvent(BaseModel):
    event: str
    data: Dict