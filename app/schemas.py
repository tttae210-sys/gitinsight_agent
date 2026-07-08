from typing import TypedDict, List, Dict, Optional, Annotated
import operator
from pydantic import BaseModel, Field

# ==========================================
# 1. LangGraph 내부 상태 관리용 스키마 (TypedDict)
# ==========================================
class InterviewState(TypedDict):
    # 1. 유저 및 레포지토리 정보
    user_id: str
    repo_url: str
    repo_commit_hash: str        # [핵심] 캐시 동기화를 위한 최신 커밋 해시

    # 2. 코드 파싱 및 RAG 검색 결과
    tech_stack: List[str]        # 추출된 기술 스택 (예: Java, Spring Boot 등)
    extracted_chunks: Annotated[List[Dict], operator.add] # [수정/유지] 검색된 코드 조각 누적

    # 3. 튜터링 루프 (모의 면접 진행 상태)
    current_question: str        # 면접관이 현재 던진 압박 질문
    answer_history: Annotated[List[str], operator.add]    # [수정/유지] 유저의 누적 답변 기록
    loop_count: int              # 힌트/재답변 루프 횟수 (최대 3회 제한)

    # 4. 평가 및 최종 결과
    evaluation: Optional[Dict]   # 답변 평가 결과 (충족 여부 및 근거)
    final_report: Optional[str]  # 최종 리팩토링 리포트 텍스트


# ==========================================
# 2. FastAPI 통신 및 DB/RAG 용 API 스키마 (Pydantic)
# ==========================================

# [API Request] 1. 프론트엔드가 최초로 레포지토리 분석을 요청할 때
class RepoAnalyzeRequest(BaseModel):
    user_id: str = Field(..., description="유저의 고유 식별자")
    repo_url: str = Field(..., description="분석할 대상 GitHub 레포지토리 URL")

# [API Request] 2. 프론트엔드가 유저의 면접 답변을 전송할 때
class ChatRequest(BaseModel):
    user_id: str = Field(..., description="유저의 고유 식별자")
    answer: str = Field(..., description="유저가 입력한 면접 답변 텍스트")

# [API Response] 3. 백엔드가 프론트엔드로 면접관의 응답을 반환할 때
class ChatResponse(BaseModel):
    current_question: Optional[str] = Field(None, description="다음 꼬리 질문 또는 압박 질문")
    evaluation: Optional[Dict] = Field(None, description="현재 답변에 대한 평가 결과 (PASS/FAIL 등)")
    final_report: Optional[str] = Field(None, description="모든 루프가 종료된 후 제공되는 최종 피드백 리포트")
    is_finished: bool = Field(False, description="면접 프로세스 전체 종료 여부")

# [DB/RAG] 4. DB 팀을 위한 벡터 DB 청크(Chunk) 데이터 구조
class DocumentChunk(BaseModel):
    file_path: str = Field(..., description="GitHub에서 추출된 파일의 경로")
    content: str = Field(..., description="코드 또는 마크다운 텍스트 원본 내용")
    metadata: Dict = Field(default_factory=dict, description="검색 성능을 높이기 위한 추가 메타데이터")
    
    user_answer: str = ""  # 🔴 추가
    retry_count: int = 0   # 🔴 추가

class ChatRequest(BaseModel):
    user_id: str
    user_answer: str          # 🔴 추가: 유저가 방금 입력한 답변
    current_retry_count: int  # 🔴 추가: 프론트에서 보낸 현재 힌트 카운트 (0~3)

class ChatResponseData(BaseModel):
    evaluation_score: int
    feedback: str
    is_finished: bool
    next_question: str
    status: str = "HINT"     # 🔴 추가: "PASS" | "HINT" | "FAIL" 상태를 내려줌
    new_retry_count: int = 0 # 🔴 추가: 새로 업데이트된 힌트 카운트를 내려줌