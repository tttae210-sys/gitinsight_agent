from typing import Optional
from pydantic import BaseModel, Field
from app.schemas import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm
from app.service.vector_service import get_vector_service


class ExtractedQuestionSchema(BaseModel):
    question: str = Field(description="지원자에게 던질 구체적인 꼬리 질문")
    file_path: Optional[str] = Field(None, description="질문 중 언급하거나 지적한 소스코드의 파일 경로")
    start_line: Optional[int] = Field(None, description="지적한 코드 영역의 시작 줄 번호 (1부터 시작)")
    end_line: Optional[int] = Field(None, description="지적한 코드 영역의 끝 줄 번호 (1부터 시작)")


def extract_interview_question(state: InterviewState) -> dict:
    """수집된 소스코드 문맥에 라인 번호를 명시하고, LLM을 통해 질문과 하이라이트 메타데이터를 함께 추출합니다."""
    llm = get_llm(temperature=0.4)
    structured_llm = llm.with_structured_output(ExtractedQuestionSchema)

    tech_stack = ", ".join(state.get("tech_stack", []))
    loop_count = state.get("loop_count", 0)
    chunks = state.get("extracted_chunks", [])
    repo_url = state.get("repo_url", "")
    answer_history = state.get("answer_history", [])

    # ── RAG 검색: tech_stack + 최근 답변 조합 쿼리로 관련 코드 추가 검색 ──────
    recent_answer = answer_history[-1] if answer_history else ""
    rag_query = f"{tech_stack} {recent_answer}".strip() or "코드 구조 및 설계"

    try:
        rag_chunks = get_vector_service().search(
            query=rag_query,
            filters={"repo_url": repo_url} if repo_url else None,
            n_results=3,
        )
    except Exception:
        rag_chunks = []
    print(f"[extractor] RAG 검색: {len(rag_chunks)}개 청크 | query: '{rag_query[:50]}'")
    # ──────────────────────────────────────────────────────────────────────────

    # ── 코드 컨텍스트 구성: state 청크 + RAG 검색 결과 (줄번호 포함) ───────────
    code_context = ""

    # (A) builder 가 state 에 남긴 원본 청크 (content/code 키 모두 지원)
    for chunk in chunks:
        file_path = chunk.get("file_path", "unknown")
        code_text = chunk.get("content") or chunk.get("code", "")
        code_context += f"--- File: {file_path} ---\n"
        for idx, line in enumerate(code_text.split("\n"), 1):
            code_context += f"{idx}: {line}\n"
        code_context += "\n"

    # (B) ChromaDB 의미 검색으로 가져온 유사 청크
    for i, rc in enumerate(rag_chunks, start=1):
        file_path = rc.get("file_path", "unknown")
        code_text = rc.get("content", "")
        code_context += f"--- [RAG #{i}] File: {file_path} ---\n"
        for idx, line in enumerate(code_text.split("\n"), 1):
            code_context += f"{idx}: {line}\n"
        code_context += "\n"

    if not code_context.strip():
        code_context = "제출된 소스코드에 분석 가능한 주요 코드 파일이 존재하지 않습니다."
    # ──────────────────────────────────────────────────────────────────────────

    # 이전 대화 기록 구성
    history_conversation = ""
    for idx, chat in enumerate(answer_history):
        role = "지원자" if idx % 2 != 0 else "면접관"
        history_conversation += f"- {role}: {chat}\n"
    if not history_conversation:
        history_conversation = "(아직 대화 기록이 없습니다. 이번이 첫 질문입니다.)"

    system_msg = (
        "당신은 강원대학교 컴퓨터공학과 학생들을 대상으로 실전 압박 기술 면접을 진행하는 "
        "IT 대기업의 10년 차 시니어 개발자 면접관입니다. 당신의 목표는 지원자가 제출한 "
        "실제 프로젝트 소스 코드를 근거로, 단순 검색으로는 답할 수 없는 날카롭고 구체적인 "
        "꼬리 질문을 던지는 것입니다.\n\n"
        f"[지원자 기술 스택]\n{tech_stack if tech_stack else '정보 없음'}\n\n"
        f"[현재까지 진행된 질문 횟수]\n{loop_count}회 (횟수가 늘어날수록 질문 난이도를 "
        "점진적으로 아키텍처/트레이드오프 수준까지 심화시키세요)\n\n"
        "[프로젝트 소스코드 문맥 (줄번호 포함)]\n"
        "{code_context}\n\n"
        "[이전 면접 대화 기록 - 중복 질문 방지용 참고자료]\n"
        "{history_conversation}\n\n"
        "[질문 생성 원칙]\n"
        "1. 반드시 위 [프로젝트 소스코드 문맥]에 실제로 존재하는 함수, 로직, 변수명, 라이브러리 "
        "사용 방식에 근거하여 질문하세요. 코드에 없는 내용을 상상하거나 지어내서 질문하지 "
        "마세요. 이는 치명적인 환각(Hallucination)입니다.\n"
        "2. 단순 정의를 묻는 질문은 절대 금지합니다.\n"
        "   - 금지 예시: '객체지향이 뭔가요?', 'REST API가 뭔가요?', 'Python은 어떤 언어인가요?'\n"
        "   - 권장 예시: '이 파일에서 반복문 안에서 매번 새로운 DB 커넥션을 여는데, 트래픽이 "
        "몰리면 어떤 문제가 발생하고 어떻게 개선하시겠어요?'\n"
        "3. 질문은 항상 '왜 이렇게 설계했는지', '이 로직에서 발생할 수 있는 문제는 무엇인지', "
        "'다른 방식과 비교했을 때 트레이드오프는 무엇인지' 중 하나 이상을 포함해야 합니다.\n"
        "4. [이전 면접 대화 기록]에 이미 나왔던 주제와 동일하거나 매우 유사한 주제는 다시 "
        "묻지 말고, 코드의 다른 영역이나 다른 관점에서 새로운 질문을 던지세요.\n"
        "5. 지원자의 직전 답변에서 기술적으로 잘못 이해한 부분이 보인다면, 그 오개념을 정확히 "
        "짚어주는 후속 질문으로 자연스럽게 이어가세요.\n"
        "6. 질문은 반드시 하나만 던지고, 두 가지 이상을 한 번에 묻지 마세요.\n\n"
        "[하이라이트(코드 지목) 규칙 - 매우 중요]\n"
        "1. 질문과 직접적으로 연관된 코드 조각이 있다면 반드시 file_path, start_line, end_line을 "
        "함께 지정하세요.\n"
        "2. start_line과 end_line은 반드시 위 [프로젝트 소스코드 문맥]에 표기된 '실제 줄 번호'와 "
        "정확히 일치해야 합니다.\n"
        "3. end_line은 항상 start_line보다 크거나 같아야 하며, 지목 범위는 질문과 직접 관련된 "
        "최소한의 코드 블록(보통 1~15줄 이내)으로 좁혀서 지정하세요.\n"
        "4. 특정 코드를 지목할 필요가 없는 일반 CS 개념/아키텍처 질문이라면 file_path, "
        "start_line, end_line을 모두 null(None)로 반환하세요.\n\n"
        "[출력 형식]\n"
        "질문은 지원자에게 직접 말하듯 자연스럽고 정중한 한국어 존댓말로 작성하고, 질문 앞뒤에 "
        "불필요한 사족이나 인사말을 붙이지 말고 질문의 핵심 내용에만 집중하세요."
    )

    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", "위 문맥과 대화 기록을 이어받아, 다음 면접 질문과 하이라이트 영역을 구성해 주세요.")
    ])

    chain = prompt | structured_llm
    response = chain.invoke({
        "code_context": code_context,
        "history_conversation": history_conversation
    })

    # 방어적 검증: start_line > end_line 같은 잘못된 조합 차단
    highlight_data = None
    if response.file_path and response.start_line is not None:
        end_line = response.end_line if response.end_line is not None else response.start_line
        if response.start_line <= end_line:
            highlight_data = {
                "file_path": response.file_path,
                "start_line": response.start_line,
                "end_line": end_line
            }

    return {
        "current_question": response.question,
        "current_highlight": highlight_data,
        "loop_count": loop_count + 1
    }
