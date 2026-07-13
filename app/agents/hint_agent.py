"""
실시간 인터랙션 에이전트: HintAgent
=====================================
역할: 지원자가 오답/포기했을 때 힌트를 제공하는 단일 책임 노드.
"""

import random
from typing import Optional
from pydantic import BaseModel, Field
from langchain_core.messages import SystemMessage, HumanMessage
from app.schemas import InterviewState
from app.core.llm import get_llm


class HintResult(BaseModel):
    hint: str = Field(description="지원자에게 제공할 힌트 메시지 (3~5문장, 정답 직접 언급 금지)")
    file_path: Optional[str] = Field(None, description="힌트와 연관된 소스코드 파일 경로")
    start_line: Optional[int] = Field(None, description="힌트 코드 영역 시작 줄 (1-indexed)")
    end_line: Optional[int] = Field(None, description="힌트 코드 영역 끝 줄 (1-indexed)")


_HINT_STYLES = [
    {
        "persona": "소크라테스식 질문으로 스스로 답을 찾게 유도하는 멘토",
        "approach": (
            "정답을 직접 말하지 말고, '왜 그렇게 했는지', '이 상황에서 어떤 문제가 생길 수 있는지' 등 "
            "연속적인 반문 형식으로 힌트를 제공하세요. 지원자가 스스로 사고를 확장할 수 있도록 유도합니다."
        ),
        "tone": "차분하고 논리적인 어조로, 지원자가 스스로 사고를 확장할 수 있도록 유도하세요.",
        "example": "나쁜 예: '비동기 처리를 사용하세요' | 좋은 예: '이 함수가 API 호출 중 blocking되는 동안 다른 요청들은 어떻게 될까요?'"
    },
    {
        "persona": "실무 경험을 바탕으로 비슷한 실패 사례를 들어주는 시니어 개발자",
        "approach": (
            "실제 현업에서 비슷한 코드 패턴으로 장애가 났던 상황을 짧게 비유로 들고, "
            "지원자의 코드에서 그와 유사한 지점을 간접적으로 짚어주세요. "
            "구체적인 라인 번호와 함께 실전 장애 사례를 언급하면 효과적입니다."
        ),
        "tone": "친근하고 경험담을 나누는 어조로, 지원자가 공감할 수 있도록 이야기하듯 설명하세요.",
        "example": (
            "과거 A회사에서 비슷한 코드로 인해 DB 커넥션이 고갈되어 전체 서비스가 30분간 다운된 사례가 있었습니다. "
            "여러분의 코드 15~20번째 줄 부분을 다시 살펴보세요."
        )
    },
    {
        "persona": "핵심 키워드 하나만 던져주는 과묵한 기술 면접관",
        "approach": (
            "힌트를 장황하게 설명하지 말고, 지원자가 검색하거나 떠올려야 할 "
            "핵심 기술 키워드나 개념어 1~2개만 짧게 언급하세요."
        ),
        "tone": "간결하고 핵심만 짚는 어조로, 단답형에 가깝게 힌트를 제공하세요.",
        "example": "'connection pooling', 'timeout 설정', 'async context manager' 이 세 가지 키워드를 검색해보세요."
    },
    {
        "persona": "코드의 특정 줄을 지목하며 '이 부분을 다시 봐'라고 안내하는 코드 리뷰어",
        "approach": (
            "소스코드 문맥에서 힌트가 될 특정 라인을 자연어로 묘사하고, "
            "그 라인이 어떤 문제와 연결될 수 있는지 간접적으로 암시하세요. "
            "코드를 직접 인용하거나 코드 블록은 사용하지 마세요."
        ),
        "tone": "코드 리뷰 피드백처럼 구체적이지만 정답은 말하지 않는 어조로 작성하세요.",
        "example": (
            "app/database.py의 커넥션 풀 설정을 보세요. max_connections이 10인데 동시 사용자가 100명이면 어떻게 될까요? "
            "connection pooling timeout 설정과 async context manager 사용을 고려해보세요."
        )
    },
    {
        "persona": "반대 상황을 가정해 역질문을 던지는 창의적 면접관",
        "approach": (
            "'만약 이 코드가 트래픽이 100배 늘어난다면?', '만약 이 함수가 동시에 1000번 호출된다면?' 처럼 "
            "극단적 가정 상황을 제시하고, 지원자 스스로 문제를 발견하게 유도하세요."
        ),
        "tone": "도전적이지만 흥미로운 어조로, 지원자의 호기심을 자극하세요.",
        "example": "'만약 이 API가 초당 10,000번 호출된다면 어떤 일이 벌어질까요? DB는 버틸 수 있을까요?'"
    },
]


def _build_code_context(chunks: list) -> str:
    context = ""
    for chunk in chunks:
        file_path = chunk.get("file_path", "unknown")
        code_text = chunk.get("content") or chunk.get("code", "")
        context += f"--- File: {file_path} ---\n"
        for idx, line in enumerate(code_text.split("\n"), 1):
            context += f"{idx}: {line}\n"
        context += "\n"
    return context.strip() or "분석 가능한 소스코드가 없습니다."


def _parse_highlight(result: HintResult) -> Optional[dict]:
    if not result.file_path or result.start_line is None:
        return None
    end = result.end_line if result.end_line is not None else result.start_line
    if result.start_line > end:
        return None
    return {"file_path": result.file_path, "start_line": result.start_line, "end_line": end}


def provide_hint(state: InterviewState) -> dict:
    """
    [실시간 에이전트] 힌트 제공 전담 노드
    
    retry_count에 따라 점진적으로 구체적인 힌트를 제공합니다:
    - 1회차: 추상적·소크라테스식 힌트
    - 2회차: 구체적·실무 사례 기반 힌트
    - 3회차: 거의 정답에 가까운 직접적 힌트
    """
    llm = get_llm(temperature=0.7)
    structured_llm = llm.with_structured_output(HintResult)

    current_question = state.get("current_question", "")
    evaluation       = state.get("evaluation", {})
    chunks           = state.get("extracted_chunks", [])
    retry_count      = state.get("retry_count", 0)  # 🔴 현재 시도 횟수
    hint_reason      = evaluation.get("reason", "")
    code_context     = _build_code_context(chunks)

    # 🔴 retry_count에 따라 힌트 스타일 선택
    if retry_count == 1:
        # 1회차: 추상적 힌트 (소크라테스식)
        style = _HINT_STYLES[0]  # 소크라테스식 질문
        hint_level = "1단계 (추상적)"
        hint_instruction = (
            "정답을 직접 말하지 말고, 지원자가 스스로 생각할 수 있도록 "
            "방향성만 제시하는 추상적 힌트를 제공하세요. "
            "핵심 키워드는 언급하되, 구체적인 구현 방법은 숨기세요.\n\n"
            f"[좋은 힌트 예시]\n{style.get('example', '')}"
        )
    elif retry_count == 2:
        # 2회차: 구체적 힌트 (실무 사례)
        style = _HINT_STYLES[1]  # 실무 경험 시니어
        hint_level = "2단계 (구체적)"
        hint_instruction = (
            "실제 코드의 특정 부분을 자연어로 지목하고, "
            "그 부분이 어떤 문제와 연결되는지 구체적으로 설명하세요. "
            "해결 방법의 70% 정도까지 힌트를 제공하세요.\n\n"
            f"[좋은 힌트 예시]\n{style.get('example', '')}"
        )
    else:
        # 3회차 이상: 거의 정답 (직접적)
        style = _HINT_STYLES[3]  # 코드 리뷰어
        hint_level = "3단계 (직접적)"
        hint_instruction = (
            "정답에 매우 가까운 직접적인 힌트를 제공하세요. "
            "코드의 정확한 라인을 지목하고, 어떻게 수정해야 하는지까지 "
            "거의 알려주되, 최종 구현 코드는 지원자가 작성하도록 남겨두세요.\n\n"
            f"[좋은 힌트 예시]\n{style.get('example', '')}"
        )

    # SystemMessage/HumanMessage 직접 사용 — ChatPromptTemplate 파싱 완전 우회
    messages = [
        SystemMessage(content=(
            f"당신은 {style['persona']}입니다.\n\n"
            f"[현재 힌트 레벨: {hint_level}]\n"
            f"{hint_instruction}\n\n"
            f"[힌트 접근 방식]\n{style['approach']}\n\n"
            f"[어조 및 스타일]\n{style['tone']}\n\n"
            f"[직전 면접 질문]\n{current_question}\n\n"
            f"[지원자 답변 평가 결과]\n{hint_reason}\n\n"
            f"[프로젝트 소스코드 문맥 (줄번호 포함)]\n{code_context}\n\n"
            "[공통 힌트 생성 원칙]\n"
            "1. 코드를 그대로 인용하거나 코드 블록을 절대 사용하지 마세요.\n"
            "2. retry_count가 높을수록 더 직접적이고 구체적으로 작성하세요.\n"
            "3. 힌트는 한 가지만, 3~5문장 이내로 간결하게 작성하세요.\n"
            "4. 지원자가 좌절하지 않도록 격려의 말을 한 마디 담아주세요.\n"
            "5. 연관 코드 영역(file_path, start_line, end_line)을 반드시 지정하세요."
        )),
        HumanMessage(content="소스코드에서 힌트 영역을 지목하고 단계적 힌트를 제공해 주세요."),
    ]

    try:
        response  = structured_llm.invoke(messages)
        hint_text = f"💡 **힌트 ({hint_level})**\n\n{response.hint}"
        highlight = _parse_highlight(response)
    except Exception as e:
        hint_text = f"💡 **힌트**\n\n소스코드에서 관련 로직을 다시 한 번 살펴보세요. ({e})"
        highlight = None

    # 🔴 힌트 표시 후 같은 질문 유지 (난이도 조절 메시지 없이 순수 재시도 표시)
    return {
        "current_question":  f"{hint_text}\n\n---\n\n**[재시도]** {current_question}",
        "current_highlight": highlight,
        "next_step":         "HINT_GIVEN",  # 🔴 명시적 완료 상태
    }
