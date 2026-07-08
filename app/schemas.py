from typing import TypedDict, List, Dict, Optional, Annotated
import operator

class InterviewState(TypedDict):
    # 1. 유저 및 레포지토리 정보
    user_id: str
    repo_url: str
    repo_commit_hash: str        # [핵심] 캐시 동기화를 위한 최신 커밋 해시

    # 2. 코드 파싱 및 RAG 검색 결과
    tech_stack: List[str]        # 추출된 기술 스택 (예: Java, Spring Boot 등)
    # [수정됨] LangGraph에서 청크가 누적되도록 operator.add 적용
    extracted_chunks: Annotated[List[Dict], operator.add] 

    # 3. 튜터링 루프 (모의 면접 진행 상태)
    current_question: str        # 면접관이 현재 던진 압박 질문
    # [수정됨] 대화 기록이 덮어씌워지지 않고 계속 누적되도록 operator.add 적용
    answer_history: Annotated[List[str], operator.add]    
    loop_count: int              # 힌트/재답변 루프 횟수 (최대 3회 제한)

    # 4. 평가 및 최종 결과
    evaluation: Optional[Dict]   # 답변 평가 결과 (충족 여부 및 근거)
    final_report: Optional[str]  # 최종 리팩토링 리포트 텍스트
    
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