import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from app.schemas import ChatRequest, ChatResponse, ChatResponseData, StreamEvent, InterviewState
from app.graph import create_graph

# APIRouter는 단 한 번만 정의하여 덮어쓰기 오류를 방지합니다.
router = APIRouter()
graph = create_graph()

def build_initial_state(request: ChatRequest) -> InterviewState:
    """Pydantic 모델(InterviewState)을 활용한 초기 상태 생성"""
    return InterviewState(
        user_id=request.user_id,
        repo_url="",  # 필요시 request 파싱하여 추가
        repo_commit_hash="",
        current_question="",
    )

@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    """동기 방식으로 전체 응답을 한 번에 반환 (데이터 모델 준수)"""
    state = build_initial_state(request)
    result = await graph.ainvoke(state)
    
    # 평가 데이터가 없을 경우를 대비한 기본값 처리
    eval_data = result.get("evaluation") or {}
    
    return ChatResponse(
        status="success",
        data=ChatResponseData(
            evaluation_score=eval_data.get("score", 0),
            feedback=eval_data.get("reason", "평가 중입니다."),
            is_finished=eval_data.get("is_satisfied", False),
            next_question=result.get("current_question", "")
        )
    )

@router.post("/chat")
async def chat_stream(request: ChatRequest):
    """SSE 스트리밍으로 각 노드의 처리 과정 실시간 전송"""
    state = build_initial_state(request)
    
    async def gen():
        final_state = None
        # 스트리밍 이벤트 처리
        async for event in graph.astream_events(state, version="v2"):
            kind = event.get("event", "")
            if kind == "on_chain_end" and event.get("name") in ("analyze", "retrieve", "respond"):
                node_name = event["name"]
                node_output = event.get("data", {}).get("output", {})
                
                # 최종 결과 추출을 위해 상태 저장
                if node_name == "respond":
                    final_state = node_output
                
                sse = StreamEvent(
                    event="node", 
                    node=node_name, 
                    data=json.dumps(node_output, ensure_ascii=False, default=str)
                )
                yield f"data: {sse.model_dump_json()}\n\n"

        # 최종 결과 전송 (구조 통일)
        if final_state:
            done_data = {
                "evaluation_score": final_state.get("evaluation", {}).get("score", 0),
                "feedback": final_state.get("evaluation", {}).get("reason", ""),
                "is_finished": final_state.get("evaluation", {}).get("is_satisfied", False),
                "next_question": final_state.get("current_question", "")
            }
            done = StreamEvent(
                event="done",
                data=json.dumps(done_data, ensure_ascii=False),
            )
            yield f"data: {done.model_dump_json()}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")