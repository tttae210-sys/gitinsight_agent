"""
전처리 에이전트: QuestionExtractorAgent
========================================
역할: builder 노드가 GitHub 코드를 수집한 직후 단 한 번 실행됩니다.
     소스코드 + 이력서를 종합 분석하여 면접 질문 풀(question_pool)을 사전에 생성합니다.

실시간 인터랙션 에이전트들은 이 풀에서 질문을 꺼내어 사용하며,
턴마다 LLM을 호출해 질문을 새로 만들지 않아도 됩니다.
"""

from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from app.schemas import InterviewState
from app.core.llm import get_llm
from app.service.vector_service import get_vector_service


# ──────────────────────────────────────────────────────────────────────────────
# 0. 구조화 출력 스키마
# ──────────────────────────────────────────────────────────────────────────────

class QuestionItem(BaseModel):
    question: str = Field(description="지원자에게 던질 기술 면접 질문 (한국어 존댓말)")
    file_path: Optional[str] = Field(None, description="질문과 연관된 소스코드 파일 경로")
    start_line: Optional[int] = Field(None, description="연관 코드 시작 줄 번호 (1-indexed)")
    end_line: Optional[int] = Field(None, description="연관 코드 끝 줄 번호 (1-indexed)")
    difficulty: str = Field(
        description="질문 난이도: 'easy' | 'medium' | 'hard'",
        default="medium"
    )


class QuestionPool(BaseModel):
    questions: list[QuestionItem] = Field(
        description="사전 생성된 기술 면접 질문 목록 (난이도 순 정렬, 최소 5개)"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 1. 코드 컨텍스트 빌더 (줄번호 포함)
# ──────────────────────────────────────────────────────────────────────────────

def _build_code_context(chunks: list, rag_chunks: list) -> str:
    """state 청크 + RAG 검색 결과를 줄번호 포함 텍스트로 조합합니다."""
    context = ""

    for chunk in chunks:
        file_path = chunk.get("file_path", "unknown")
        code_text = chunk.get("content") or chunk.get("code", "")
        context += f"--- File: {file_path} ---\n"
        for idx, line in enumerate(code_text.split("\n"), 1):
            context += f"{idx}: {line}\n"
        context += "\n"

    for i, rc in enumerate(rag_chunks, start=1):
        file_path = rc.get("file_path", "unknown")
        code_text = rc.get("content", "")
        context += f"--- [RAG #{i}] File: {file_path} ---\n"
        for idx, line in enumerate(code_text.split("\n"), 1):
            context += f"{idx}: {line}\n"
        context += "\n"

    return context.strip() or "분석 가능한 소스코드 파일이 없습니다."


# ──────────────────────────────────────────────────────────────────────────────
# 2. 전처리 노드 메인 함수
# ──────────────────────────────────────────────────────────────────────────────

def extract_question_pool(state: InterviewState) -> dict:
    """
    [전처리 에이전트] 코드 분석 → 질문 풀 사전 생성

    builder 실행 후 1회만 호출됩니다.
    - 소스코드 전체 + 이력서를 LLM에 한 번에 던져 5~7개의 질문을 미리 만들어둡니다.
    - 이후 실시간 인터랙션 에이전트(evaluator 흐름)는 이 풀에서 순서대로 꺼내씁니다.
    """
    llm = get_llm(temperature=0.8)
    structured_llm = llm.with_structured_output(QuestionPool)

    tech_stack = ", ".join(state.get("tech_stack", []))
    chunks = state.get("extracted_chunks", [])
    repo_url = state.get("repo_url", "")

    # ── 이력서 포맷팅 ──────────────────────────────────────────────────────────
    resume_text = state.get("resume_text", "")
    if resume_text:
        safe_resume = resume_text.replace("{", "{{").replace("}", "}}")
        resume_context = (
            f"--- [지원자 이력서 (Resume)] ---\n{safe_resume}\n"
            "--------------------------------"
        )
    else:
        resume_context = "제공된 이력서가 없습니다. 소스코드 분석 중심의 질문을 생성하세요."

    # ── RAG 보강 검색 ──────────────────────────────────────────────────────────
    rag_query = tech_stack or "코드 구조 및 설계"
    try:
        rag_chunks = get_vector_service().search(
            query=rag_query,
            filters={"repo_url": repo_url} if repo_url else None,
            n_results=3,
        )
    except Exception:
        rag_chunks = []

    code_context = _build_code_context(chunks, rag_chunks)

    # ── 프롬프트 ───────────────────────────────────────────────────────────────
    system_msg = (
        "당신은 IT 대기업의 10년 차 시니어 기술 면접관입니다.\n"
        "아래 지원자의 프로젝트 소스코드와 이력서를 철저히 분석하여, "
        "실전 압박 기술 면접 질문 풀(pool)을 사전에 생성하는 것이 임무입니다.\n\n"
        f"[지원자 기술 스택]\n{tech_stack or '정보 없음'}\n\n"
        f"{resume_context}\n\n"
        f"[프로젝트 소스코드 문맥 (줄번호 포함)]\n{code_context}\n\n"
        "[질문 풀 생성 원칙]\n"
        "1. 질문은 반드시 소스코드 또는 이력서의 실제 내용에 근거해야 합니다. "
        "   존재하지 않는 로직을 상상해서 만들지 마세요.\n"
        "2. 단순 이론/정의 질문('REST API란 무엇인가요?')은 금지합니다. "
        "   반드시 코드의 구체적인 지점을 파고드는 질문을 만드세요.\n"
        "3. 난이도를 easy → medium → hard 순으로 점진적으로 배치하세요.\n"
        "4. 이력서와 코드 사이의 괴리(주장 vs 구현)를 날카롭게 짚는 질문을 최소 1개 포함하세요.\n"
        "5. 동시성/예외처리/메모리/성능/아키텍처 관련 트레이드오프를 다루는 질문을 최소 1개 포함하세요.\n"
        "6. 질문은 최소 5개, 최대 7개 생성하세요.\n"
        "7. 연관 코드가 있다면 file_path, start_line, end_line을 정확히 지정하세요 (1~15줄 범위).\n"
        "8. 모든 질문은 한국어 존댓말로 작성하세요."
    )

    messages = [
        SystemMessage(content=system_msg),
        HumanMessage(content="위 소스코드와 이력서를 분석하여 면접 질문 풀을 생성해 주세요."),
    ]

    try:
        response = structured_llm.invoke(messages)
        question_pool = [
            {
                "question": q.question,
                "file_path": q.file_path,
                "start_line": q.start_line,
                "end_line": q.end_line,
                "difficulty": q.difficulty,
            }
            for q in response.questions
        ]
    except Exception as e:
        # 풀 생성 실패 시 기본 질문 1개로 폴백
        question_pool = [
            {
                "question": (
                    "제출하신 프로젝트의 핵심 기술 선택 이유와 "
                    "해당 기술을 사용하면서 겪었던 가장 어려운 기술적 문제는 무엇이었나요?"
                ),
                "file_path": None,
                "start_line": None,
                "end_line": None,
                "difficulty": "easy",
            }
        ]
        print(f"[question_extractor] 질문 풀 생성 실패, 폴백 사용: {e}")

    print(f"[question_extractor] 질문 풀 {len(question_pool)}개 생성 완료")

    # 첫 번째 질문을 current_question으로 바로 세팅
    first = question_pool[0] if question_pool else {}
    first_question = first.get("question", "")
    first_highlight = None
    if first.get("file_path") and first.get("start_line") is not None:
        end = first.get("end_line") or first.get("start_line")
        if first["start_line"] <= end:
            first_highlight = {
                "file_path": first["file_path"],
                "start_line": first["start_line"],
                "end_line": end,
            }

    return {
        "question_pool": question_pool[1:],   # 첫 질문은 꺼냈으므로 나머지만 저장
        "current_question": first_question,
        "current_highlight": first_highlight,
        "loop_count": 1,
    }
