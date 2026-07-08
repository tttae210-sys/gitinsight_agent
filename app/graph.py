import os
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver  
from app.schemas import InterviewState

# 에이전트 노드 함수 임포트
from app.agents.builder import build_github_repo
from app.agents.classifier import classify_user_intent
from app.agents.extractor import extract_interview_question

try:
    from app.agents.feedback import evaluate_answer
except ImportError:
    def evaluate_answer(state: InterviewState) -> dict:
        user_ans = state.get("answer_history", [""])[-1]
        retry = state.get("retry_count", 0)
        if "redis" in user_ans.lower() or "cache" in user_ans.lower() or "메모리" in user_ans:
            return {
                "evaluation": {
                    "score": 9, 
                    "passed": True, 
                    "reason": "Redis 캐시 사용 목적과 인메모리 분산 저장에 대해 올바르게 답변하셨습니다."
                },
                "next_step": "PASS",
                "retry_count": 0
            }
        else:
            new_retry = retry + 1
            return {
                "evaluation": {
                    "score": 4, 
                    "passed": False, 
                    "reason": "Redis와 로컬 메모리 캐시의 차이점에 대한 기술적 설명이 부족합니다."
                },
                "next_step": "HINT" if new_retry < 3 else "FAIL",
                "retry_count": new_retry
            }

def chat_node(state: InterviewState) -> dict:
    user_input = state["answer_history"][-1] if state.get("answer_history") else ""
    response = "안녕하세요! GitInsight AI 모의 면접관입니다. 면접을 시작하시려면 좌측 설정창에 GitHub Repository URL을 입력해 주세요."
    return {
        "current_question": response,
        "next_step": "CHAT_DONE"
    }

def route_after_classifier(state: InterviewState) -> str:
    return state.get("next_step", "CHAT")

def route_after_evaluation(state: InterviewState) -> str:
    next_step = state.get("next_step", "HINT")
    if next_step == "PASS":
        return "extractor"
    elif next_step == "HINT":
        return "extractor"
    else:
        return END

def create_graph():
    """FastAPI에서 세션 상태를 정상 추적할 수 있도록 내부 메모리 체크포인터를 결합해 컴파일합니다."""
    workflow = StateGraph(InterviewState)
    
    # 노드 등록
    workflow.add_node("classifier", classify_user_intent)
    workflow.add_node("builder", build_github_repo)
    workflow.add_node("extractor", extract_interview_question)
    workflow.add_node("evaluator", evaluate_answer)
    workflow.add_node("chat", chat_node)
    
    # 시작점 지정
    workflow.set_entry_point("classifier")
    
    # 조건부 및 일반 엣지 연결
    workflow.add_conditional_edges(
        "classifier",
        route_after_classifier,
        {
            "START": "builder",
            "ANSWER": "evaluator",
            "CHAT": "chat"
        }
    )
    workflow.add_edge("builder", "extractor")
    workflow.add_edge("chat", END)
    
    workflow.add_conditional_edges(
        "evaluator",
        route_after_evaluation,
        {
            "extractor": "extractor",
            END: END
        }
    )
    workflow.add_edge("extractor", END)
    
    # 체크포인터 등록
    memory = MemorySaver()
    return workflow.compile(checkpointer=memory)