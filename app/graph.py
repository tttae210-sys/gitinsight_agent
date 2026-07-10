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
    question_pool에서 다음 질문을 꺼내 current_question에 세팅합니다.
    풀이 비어 있으면 면접 종료 신호(next_step='REPORT')를 반환합니다.
    """
    pool = list(state.get("question_pool", []))

    if not pool:
        return {"next_step": "REPORT"}

    next_q   = pool.pop(0)
    question = next_q.get("question", "")
    highlight = None
    if next_q.get("file_path") and next_q.get("start_line") is not None:
        end = next_q.get("end_line") or next_q.get("start_line")
        if next_q["start_line"] <= end:
            highlight = {
                "file_path":  next_q["file_path"],
                "start_line": next_q["start_line"],
                "end_line":   end,
            }

    return {
        "current_question":  question,
        "current_highlight": highlight,
        "question_pool":     pool,
        "retry_count":       0,
        "loop_count":        state.get("loop_count", 1) + 1,
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
