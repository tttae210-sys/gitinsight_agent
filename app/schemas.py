from typing import List, Dict, Any, Optional, TypedDict
from pydantic import BaseModel


# ==========================================
# 0. HighlightMetadata 규격 정의
# ==========================================
class HighlightMetadata(BaseModel):
    file_path: Optional[str] = None   # 하이라이트할 파일 경로 (예: "app/main.py")
    start_line: Optional[int] = None  # 시작 줄 번호 (1-indexed)
    end_line: Optional[int] = None    # 끝 줄 번호 (1-indexed)


# ==========================================
# 1. LangGraph 에이전트 인터뷰 상태 정의 (TypedDict)
# ==========================================
class InterviewState(TypedDict, total=False):
    user_id: str
    repo_url: Optional[str]
    repo_commit_hash: Optional[str]  # 🔴 현재 분석 중인 레포의 커밋 해시 (캐시 key)
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
    resume_text: Optional[str]  # 📄 에이전트 노드들이 참조할 이력서 원본 텍스트
    target_company: Optional[str]  # 🏢 목표 회사
    target_field: Optional[str]    # 🎯 목표 분야/직군  
    company_values: Optional[str]  # 💡 기업 인재상/핵심 가치

    # ── 전처리 에이전트가 사전에 생성한 질문 풀 ──────────────────────────────
    # question_extractor 가 코드 분석 후 생성한 면접 질문 목록.
    # 실시간 인터랙션 에이전트(evaluator 등)는 이 풀에서 질문을 꺼내어 사용합니다.
    question_pool: List[Dict[str, Any]]  # [{"question": str, "file_path": str|None, "start_line": int|None, "end_line": int|None}, ...]


# ==========================================
# 2. FastAPI 요청(Request) 규격 정의
# ==========================================
class ChatRequest(BaseModel):
    user_id: str
    user_answer: str
    current_retry_count: int = 0
    repo_url: Optional[str] = None
    resume_text: Optional[str] = None  # 📄 프론트엔드에서 파싱해 보내주는 이력서 텍스트
    target_company: Optional[str] = None  # 🏢 목표 회사
    target_field: Optional[str] = None    # 🎯 목표 분야/직군
    company_values: Optional[str] = None  # 💡 기업 인재상/핵심 가치


class ResetRequest(BaseModel):
    user_id: str  # 리셋할 LangGraph 스레드 ID


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
    event: str                   # 이벤트 타입 ("status", "result", "error")
    node: Optional[str] = None   # 현재 실행 중인 에이전트 노드 단계
    message: str = ""            # 화면 스피너에 실시간 출력할 멘트
    data: Optional[Any] = None   # 최종 전달할 데이터 패키지
