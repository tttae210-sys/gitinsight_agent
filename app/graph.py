from langgraph.graph import StateGraph, END
from app.schemas import InterviewState
from app.core.config import Config

# 에이전트 노드들 불러오기
from app.agents.query_analyzer import intent_classifier_node
from app.agents.retrieval import code_build_node, interview_extract_node
from app.agents.responder import evaluation_node, feedback_gen_node

def route_from_intent(state: InterviewState):
    """URL 유무에 따라 메인 파이프라인으로 갈지 종료할지 결정하는 라우터"""
    if state.get("repo_url"):
        print("[ROUTE] URL 감지 완료 -> CodeBuildAgent로 이동")
        return "code_build"
    print("[ROUTE] 일반 대화 -> 프로세스 종료 (유저 응답 대기)")
    return END

def route_from_eval(state: InterviewState):
    """답변 평가 결과와 루프 카운트에 따라 탈출할지 다시 질문할지 결정하는 라우터"""
    eval_result = state.get("evaluation", {})
    status = eval_result.get("status", "FAIL")
    loop_count = state.get("loop_count", 0)

    if status == "PASS" or loop_count >= Config.MAX_LOOP_COUNT:
        print(f"[ROUTE] 평가 충족 또는 최대 루프({loop_count}회) 도달 -> 최종 피드백 생성")
        return "feedback_gen"
    
    print(f"[ROUTE] 평가 미충족 (루프 {loop_count}회) -> 추가 압박 힌트 질문으로 재순환")
    return "interview_extract"

# 1. 그래프(StateGraph) 초기화
workflow = StateGraph(InterviewState)

# 2. 노드(에이전트) 등록
workflow.add_node("intent_classifier", intent_classifier_node)
workflow.add_node("code_build", code_build_node)
workflow.add_node("interview_extract", interview_extract_node)
workflow.add_node("evaluation", evaluation_node)
workflow.add_node("feedback_gen", feedback_gen_node)

# 3. 엣지(흐름) 연결
# 시작점 설정
workflow.set_entry_point("intent_classifier")

# 의도 분석 -> URL 유무에 따른 분기
workflow.add_conditional_edges(
    "intent_classifier",
    route_from_intent,
    {
        "code_build": "code_build",
        END: END
    }
)

# 코드 빌드 완료 후 바로 질문 추출 단계로 이동
workflow.add_edge("code_build", "interview_extract")

# 면접 질문 출제 후 평가로 이동 (실제 서비스에서는 이 사이에 유저 입력을 받는 인터럽트가 들어갑니다)
workflow.add_edge("interview_extract", "evaluation")

# 평가 결과 -> 튜터링 루프(재순환) 또는 최종 리포트로 분기
workflow.add_conditional_edges(
    "evaluation",
    route_from_eval,
    {
        "feedback_gen": "feedback_gen",
        "interview_extract": "interview_extract"
    }
)

# 피드백 생성 완료 후 프로세스 종료
workflow.add_edge("feedback_gen", END)

# 4. 그래프 컴파일
app = workflow.compile()

# ... (기존 코드 app = workflow.compile() 아래에 이어붙이기) ...

if __name__ == "__main__":
    print("\n[SYSTEM] '이게뭐조' 멀티 에이전트 워크플로우 시스템을 시작합니다...")
    
    # 테스트용 초기 상태 (URL이 없는 일반 인사말을 던져봅니다)
    initial_state = {
        "answer_history": ["안녕하세요? 이거 사용하면 진짜 대기업 기술 면접 잘 보게 도와주나요?"],
        "repo_url": "",
        "repo_commit_hash": "",
        "tech_stack": [],
        "extracted_chunks": [],
        "current_question": "",
        "loop_count": 0
    }
    
    # 노드가 하나씩 실행될 때마다 결과를 화면에 출력 (스트리밍)
    for output in app.stream(initial_state, {"recursion_limit": 10}):
        for node_name, node_state in output.items():
            print(f"\n====================================")
            print(f"🔄 [실행된 에이전트 노드: {node_name}]")
            print(f"====================================")
            print(node_state)
            
    print("\n[SYSTEM] 워크플로우 종료.")