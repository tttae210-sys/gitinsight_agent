"""
LangGraph 워크플로우
=====================
에이전트 역할 분리 구조:

[전처리 — 세션 시작 시 1회]
  classifier → builder → question_extractor
                              │
                              └─ question_pool(5~7개) + current_question 세팅 → END

[실시간 인터랙션 — 매 턴]
  classifier
    ├─ ANSWER      → evaluator
    │                   ├─ PASS          → next_question_node → END
    │                   ├─ HINT          → hint_agent        → END
    │                   ├─ FAIL          → reporter          → END
    │                   └─ ANSWER_REQUEST→ answer_provider   → END
    ├─ ANSWER_REQUEST → answer_provider → END
    ├─ SKIP           → next_question_node → END
    └─ CHAT           → chat_node          → END
"""

from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver

from app.schemas import InterviewState

# ── 전처리 에이전트 ────────────────────────────────────────────────────────────
from app.agents.builder import build_github_repo
from app.agents.question_extractor import extract_question_pool

# ── 실시간 인터랙션 에이전트 ──────────────────────────────────────────────────
from app.agents.classifier import classify_user_intent
from app.agents.evaluator import evaluate_answer
from app.agents.hint_agent import provide_hint
from app.agents.answer_provider import provide_answer
from app.agents.reporter import generate_final_report


# ──────────────────────────────────────────────────────────────────────────────
# 보조 노드
# ──────────────────────────────────────────────────────────────────────────────

def chat_node(state: InterviewState) -> dict:
    """초기 진입 시 레포 URL 입력을 유도하는 기본 캐주얼 챗 노드."""
    return {
        "current_question": (
            "안녕하세요! GitInsight AI 모의 면접관입니다. "
            "면접을 시작하시려면 좌측 설정창에 GitHub Repository URL을 입력해 주세요."
        ),
        "next_step": "CHAT_DONE",
    }


def next_question_node(state: InterviewState) -> dict:
    """
    적응형 난이도 조절 시스템:
    - 첫 질문은 question_pool에서 꺼냄
    - 이후 질문은 이전 답변의 점수를 기반으로 실시간 생성
    
    점수별 난이도 조절:
    - 1~4점: Easy (기초 개념 재확인)
    - 5~7점: Medium (현재 수준 유지)
    - 8~10점: Hard (심화 개념 도전)
    """
    pool = list(state.get("question_pool", []))
    loop_count = state.get("loop_count", 0)
    evaluation = state.get("evaluation", {})
    last_score = evaluation.get("score", 5)  # 기본값 5점
    
    # 🔴 질문 풀이 비어있으면 면접 종료
    if not pool:
        return {"next_step": "REPORT"}

    # 🔴 적응형 난이도 판정
    if last_score <= 4:
        target_difficulty = "easy"
        difficulty_msg = "이전 답변이 부족했으므로 기초 개념을 다시 확인합니다."
    elif last_score <= 7:
        target_difficulty = "medium"
        difficulty_msg = "현재 수준을 유지하여 중급 질문을 드립니다."
    else:
        target_difficulty = "hard"
        difficulty_msg = "훌륭한 답변입니다! 한 단계 더 심화된 질문을 드립니다."

    # 🔴 난이도에 맞는 질문 선택 (없으면 첫 번째 질문)
    selected_question = None
    remaining_pool = []
    
    for q in pool:
        if q.get("difficulty", "medium") == target_difficulty and not selected_question:
            selected_question = q
        else:
            remaining_pool.append(q)
    
    # 원하는 난이도가 없으면 풀의 첫 번째 질문 사용
    if not selected_question:
        selected_question = pool[0]
        remaining_pool = pool[1:]

    question = selected_question.get("question", "")
    highlight = None
    if selected_question.get("file_path") and selected_question.get("start_line") is not None:
        end = selected_question.get("end_line") or selected_question.get("start_line")
        if selected_question["start_line"] <= end:
            highlight = {
                "file_path":  selected_question["file_path"],
                "start_line": selected_question["start_line"],
                "end_line":   end,
            }

    # 🔴 난이도 조절 메시지 추가
    if loop_count > 0:  # 첫 질문이 아니면 난이도 메시지 표시
        question = f"**[난이도 조절: {target_difficulty.upper()}]**\n{difficulty_msg}\n\n---\n\n{question}"

    return {
        "current_question":  question,
        "current_highlight": highlight,
        "question_pool":     remaining_pool,
        "retry_count":       0,
        "loop_count":        loop_count + 1,
        "next_step":         "NEXT_QUESTION_DONE",
    }


# ──────────────────────────────────────────────────────────────────────────────
# 라우터 함수
# ──────────────────────────────────────────────────────────────────────────────

def route_after_classifier(state: InterviewState) -> str:
    """
    classifier 결과(next_step)에 따라 분기합니다.
      START          → builder (전처리 파이프라인 시작)
      ANSWER         → evaluator
      ANSWER_REQUEST → answer_provider
      SKIP           → next_question
      CHAT           → chat
    """
    return state.get("next_step", "CHAT")


def route_after_evaluator(state: InterviewState) -> str:
    """
    evaluator 채점 결과에 따라 분기합니다.
      PASS           → next_question (다음 질문 꺼내기)
      HINT           → hint_agent
      FAIL           → reporter (최종 리포트)
      ANSWER_REQUEST → answer_provider
    """
    next_step = state.get("next_step", "HINT")
    if next_step == "PASS":
        return "next_question"
    if next_step in ("HINT", "SURRENDER"):
        return "hint_agent"
    if next_step == "ANSWER_REQUEST":
        return "answer_provider"
    return "reporter"   # FAIL


def route_after_next_question(state: InterviewState) -> str:
    """
    next_question_node 실행 후 분기합니다.
      REPORT → reporter (풀 소진, 면접 종료)
      그 외  → END
    """
    return "reporter" if state.get("next_step") == "REPORT" else "end"


# ──────────────────────────────────────────────────────────────────────────────
# 그래프 빌드
# ──────────────────────────────────────────────────────────────────────────────

def create_graph():
    """MemorySaver 체크포인터와 함께 그래프를 컴파일합니다."""
    workflow = StateGraph(InterviewState)

    # ── 노드 등록 ──────────────────────────────────────────────────────────────
    # 전처리
    workflow.add_node("classifier",         classify_user_intent)
    workflow.add_node("builder",            build_github_repo)
    workflow.add_node("question_extractor", extract_question_pool)   # 신규: 질문 풀 사전 생성

    # 실시간 인터랙션
    workflow.add_node("evaluator",          evaluate_answer)         # 신규: 채점 전담
    workflow.add_node("hint_agent",         provide_hint)            # 신규: 힌트 전담
    workflow.add_node("answer_provider",    provide_answer)          # 신규: 모범 답안 전담
    workflow.add_node("reporter",           generate_final_report)   # 신규: 리포트 전담
    workflow.add_node("next_question",      next_question_node)      # 신규: 다음 질문 꺼내기
    workflow.add_node("chat",               chat_node)

    # ── 시작점 ─────────────────────────────────────────────────────────────────
    workflow.set_entry_point("classifier")

    # ── 엣지 연결 ─────────────────────────────────────────────────────────────
    # classifier → 분기
    workflow.add_conditional_edges(
        "classifier",
        route_after_classifier,
        {
            "START":          "builder",
            "ANSWER":         "evaluator",
            "ANSWER_REQUEST": "answer_provider",
            "SKIP":           "next_question",
            "CHAT":           "chat",
        },
    )

    # 전처리 파이프라인: builder → question_extractor → END
    workflow.add_edge("builder",            "question_extractor")
    workflow.add_edge("question_extractor", END)

    # 실시간: evaluator → 분기
    workflow.add_conditional_edges(
        "evaluator",
        route_after_evaluator,
        {
            "next_question":  "next_question",
            "hint_agent":     "hint_agent",
            "answer_provider":"answer_provider",
            "reporter":       "reporter",
        },
    )

    # next_question → 분기 (풀 소진 시 reporter, 아니면 END)
    workflow.add_conditional_edges(
        "next_question",
        route_after_next_question,
        {
            "reporter": "reporter",
            "end":      END,
        },
    )

    # 단말 노드
    workflow.add_edge("hint_agent",      END)
    workflow.add_edge("answer_provider", END)
    workflow.add_edge("reporter",        END)
    workflow.add_edge("chat",            END)

    # ── 컴파일 ────────────────────────────────────────────────────────────────
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)
