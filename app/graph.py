import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
from app.schemas import InterviewState

# 에이전트 노드 함수 임포트
from app.agents.builder import build_github_repo
from app.agents.classifier import classify_user_intent
from app.agents.extractor import extract_interview_question
from app.agents.feedback import evaluate_answer, generate_final_report, provide_answer


# ==========================================
# 보조 노드
# ==========================================
def chat_node(state: InterviewState) -> dict:
    """초기 진입 시 레포 URL 입력을 유도하는 기본 캐주얼 챗 노드입니다."""
    response = "안녕하세요! GitInsight AI 모의 면접관입니다. 면접을 시작하시려면 좌측 설정창에 GitHub Repository URL을 입력해 주세요."
    return {
        "current_question": response,
        "next_step": "CHAT_DONE"
    }


# ==========================================
# 라우터 함수
# ==========================================
def route_after_classifier(state: InterviewState) -> str:
    """인텐트 분류 결과에 따라 빌더(START), 채점기(ANSWER), 질문 스킵(SKIP), 캐주얼챗(CHAT) 경로를 나눕니다."""
    return state.get("next_step", "CHAT")


def route_after_evaluation(state: InterviewState) -> str:
    """
    [핵심 분기 제어]
    - PASS 또는 HINT: 다음 면접 질문 추출 노드로 이동
    - ANSWER_GIVEN: 정답을 직접 알려준 경우 → END로 바로 종료
    - FAIL (3-Strike 아웃): 최종 리포트 작성 노드(reporter)로 강제 트랙 전환
    """
    next_step = state.get("next_step", "HINT")
    if next_step == "ANSWER_GIVEN":
        return "end"
    elif next_step in ("PASS", "HINT"):
        return "extractor"
    else:
        return "reporter"


# ==========================================
# 그래프 빌드
# ==========================================
def create_graph():
    """FastAPI에서 세션 상태를 정상 추적할 수 있도록 내부 메모리 체크포인터를 결합해 컴파일합니다."""
    workflow = StateGraph(InterviewState)

    # 1. 노드 등록
    workflow.add_node("classifier", classify_user_intent)
    workflow.add_node("builder", build_github_repo)
    workflow.add_node("extractor", extract_interview_question)
    workflow.add_node("evaluator", evaluate_answer)
    workflow.add_node("answer_provider", provide_answer)
    workflow.add_node("chat", chat_node)
    workflow.add_node("reporter", generate_final_report)

    # 2. 시작점 지정
    workflow.set_entry_point("classifier")

    # 3. 엣지 연결
    workflow.add_conditional_edges(
        "classifier",
        route_after_classifier,
        {
            "START": "builder",
            "ANSWER": "evaluator",
            "ANSWER_REQUEST": "answer_provider",
            "SKIP": "extractor",
            "CHAT": "chat"
        }
    )
    workflow.add_edge("builder", "extractor")
    workflow.add_edge("chat", END)
    workflow.add_edge("answer_provider", END)

    # 채점 후 분기: extractor(다음 질문) 또는 reporter(최종 리포트)
    workflow.add_conditional_edges(
        "evaluator",
        route_after_evaluation,
        {
            "extractor": "extractor",
            "reporter": "reporter",
            "end": END
        }
    )
    workflow.add_edge("extractor", END)
    workflow.add_edge("reporter", END)  # 리포트 도출 완료 시 면접 종료

    # 4. 체크포인터 등록 후 컴파일
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)
