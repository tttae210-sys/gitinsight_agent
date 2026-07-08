from typing import List, Dict, Any, Optional, TypedDict
from pydantic import BaseModel

# ==========================================
# 0. HighlightMetadata 규격 정의
# ==========================================
class HighlightMetadata(BaseModel):
    file_path: Optional[str] = None  # 하이라이트할 파일 경로 (예: "app/main.py")
    start_line: Optional[int] = None # 시작 줄 번호 (1-indexed)
    end_line: Optional[int] = None   # 끝 줄 번호 (1-indexed)

# ==========================================
# 1. LangGraph 에이전트 인터뷰 상태 정의 (TypedDict)
# ==========================================
class InterviewState(TypedDict, total=False):
    user_id: str
    repo_url: Optional[str]
    tech_stack: List[str]
    extracted_chunks: List[Dict[str, Any]]
    answer_history: List[str]
    current_question: str
    loop_count: int
    retry_count: int
    evaluation: Dict[str, Any]
    final_report: str
    next_step: str
    current_highlight: Optional[Dict[str, Any]]

# ==========================================
# 2. FastAPI 요청(Request) 규격 정의
# ==========================================
class ChatRequest(BaseModel):
    user_id: str
    user_answer: str
    current_retry_count: int = 0
    repo_url: Optional[str] = None

# ==========================================
# 3. FastAPI 동기식 응답(Response) 규격 정의
# ==========================================
class ChatResponseData(BaseModel):
    feedback: str
    next_question: str
    new_retry_count: int
    status: str
    highlight: Optional[HighlightMetadata] = None
    tech_stack: Optional[List[str]] = None
    extracted_chunks: Optional[List[Dict[str, Any]]] = None
    evaluation: Optional[Dict[str, Any]] = None
    final_report: Optional[str] = None

class ChatResponse(BaseModel):
    status: str = "success"
    data: ChatResponseData

# ==========================================
# 4. SSE 스트리밍용 이벤트 규격 정의
# ==========================================
class StreamEvent(BaseModel):
    event: str                  # 이벤트 타입 (예: "node", "done", "error")
    node: Optional[str] = None  # 현재 실행 중인 에이전트 단계
    data: Any                   # 실시간 전송 데이터