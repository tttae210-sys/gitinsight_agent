from app.schemas import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm
from app.service.vector_service import get_vector_service

def extract_interview_question(state: InterviewState) -> dict:
    """수집된 소스코드 문맥과 답변 히스토리를 바탕으로 맞춤형 기술 면접 질문을 생성합니다."""
    llm = get_llm(temperature=0.7) # 질문의 다양성을 위해 온도를 살짝 올림
    
    # 상태값 꺼내기
    tech_stack_list = state.get("tech_stack", [])
    tech_stack = ", ".join(tech_stack_list)
    loop_count = state.get("loop_count", 0)
    chunks = state.get("extracted_chunks", [])
    repo_url = state.get("repo_url", "")
    commit_hash = state.get("repo_commit_hash", "")
    answer_history = state.get("answer_history", [])

    # ── RAG 검색: tech_stack + 최근 답변을 조합한 쿼리로 관련 코드 3개 검색 ────
    # 최근 유저 답변이 있으면 그것을 우선 쿼리로, 없으면 기술 스택으로 대체
    recent_answer = answer_history[-1] if answer_history else ""
    rag_query = f"{tech_stack} {recent_answer}".strip() or "코드 구조 및 설계"

    filters = {"repo_url": repo_url} if repo_url else None
    if repo_url and commit_hash:
        filters = {"$and": [{"repo_url": repo_url}, {"commit_hash": commit_hash}]}

    rag_chunks = get_vector_service().search(
        query=rag_query,
        filters=filters,
        n_results=3,
    )
    print(f"[extractor] RAG 검색: {len(rag_chunks)}개 청크 | query: '{rag_query[:50]}...'")
    # ──────────────────────────────────────────────────────────────────────────

    # ── 코드 컨텍스트 구성: state 청크(빌더 수집분) + RAG 검색 결과 ─────────────
    code_context_parts: list[str] = []

    # (A) builder 가 state 에 남긴 원본 청크
    for chunk in chunks:
        code_context_parts.append(
            f"### [수집 코드] {chunk.get('file_path', '')}\n"
            f"```\n{chunk.get('code', '')}\n```"
        )

    # (B) ChromaDB 에서 의미 검색으로 가져온 유사 청크
    for i, rc in enumerate(rag_chunks, start=1):
        code_context_parts.append(
            f"### [RAG 검색 #{i}] {rc.get('file_path', '')}\n"
            f"```\n{rc.get('content', '')}\n```"
        )

    code_context = (
        "\n\n".join(code_context_parts)
        if code_context_parts
        else "제출된 소스코드에 분석 가능한 파이썬 또는 주요 코드 파일이 존재하지 않습니다."
    )
    # ──────────────────────────────────────────────────────────────────────────

    # 면접관 페르소나 및 지침 하드코딩 (이해하기 쉽게 한 번에 하나씩 질문)
    system_msg = (
        "당신은 강원대학교 컴퓨터공학과 학생들을 위해 기술 면접을 진행하는 아주 정교하고 날카로운 IT 대기업의 시니어 면접관 선배입니다.\n"
        f"지원자의 기술 스택({tech_stack})과 그들이 직접 작성한 아래 [프로젝트 소스코드 문맥]을 철저히 분석하여 전공자 수준의 질문을 던지세요.\n\n"
        "[프로젝트 소스코드 문맥]\n"
        f"{code_context}\n\n"
        "지침:\n"
        "1. 절대 추상적인 질문을 하지 말고, 위 소스코드에서 유저가 사용한 라이브러리, 함수 구조, 자료구조, 예외 처리 방식 등 '진짜 코드 기반'의 꼬리 질문을 던지세요.\n"
        f"2. 현재 질문 회차는 {loop_count + 1}회차입니다. (최대 3회 진행 예정)\n"
        "3. 만약 이전 답변 히스토리가 있다면, 유저가 한 답변의 허점을 찌르거나 더 깊은 CS 지식(메모리 관리, 시간복잡도 등)을 물어보는 꼬리 질문을 던지세요.\n"
        "4. 코드 문맥이 부족하면 멈추지 말고 기술 스택 기반의 표준 CS/전공 기초 질문으로 전환하세요.\n"
        "5. 전공생이 이해하기 쉽도록 문맥을 잘 정리하고, 반드시 '한 번에 딱 한 가지 질문만' 던지세요."
    )
    
    # 대화 히스토리 구성 (위 RAG 블록에서 이미 꺼낸 answer_history 재사용)
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", f"이전 면접 대화 기록: {answer_history}\n\n위 문맥을 이어받아 다음 면접 질문을 하나만 생성해 주세요.")
    ])
    
    chain = prompt | llm
    response = chain.invoke({})
    
    return {
        "current_question": response.content.strip(),
        "loop_count": loop_count + 1
    }
