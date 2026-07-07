from typing import TypedDict, List, Dict, Optional

class InterviewState(TypedDict):
    # 1. 유저 및 레포지토리 정보
    user_id: str
    repo_url: str
    repo_commit_hash: str        # [핵심] 캐시 동기화를 위한 최신 커밋 해시

    # 2. 코드 파싱 및 RAG 검색 결과
    tech_stack: List[str]        # 추출된 기술 스택 (예: Java, Spring Boot 등)
    extracted_chunks: List[Dict] # 검색된 핵심 코드 조각 및 족보 데이터

    # 3. 튜터링 루프 (모의 면접 진행 상태)
    current_question: str        # 면접관이 현재 던진 압박 질문
    answer_history: List[str]    # 유저의 누적 답변 기록 (컨텍스트 유지용)
    loop_count: int              # 힌트/재답변 루프 횟수 (최대 3회 제한)

    # 4. 평가 및 최종 결과
    evaluation: Optional[Dict]   # 답변 평가 결과 (충족 여부 및 근거)
    final_report: Optional[str]  # 최종 리팩토링 리포트 텍스트