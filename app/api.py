import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from app.schemas import ChatRequest, ChatResponse, StreamEvent
from app.graph import create_graph

# APIRouter는 단 한 번만 정의하여 덮어쓰기 오류를 방지합니다.
router = APIRouter()
graph = create_graph()

def build_initial_state(query: str, repo_url: str = None, user_id: str = None) -> dict:
    """사용자 메시지 및 설정을 기반으로 그래프 초기 상태(State)를 생성합니다."""
    return {
        "messages": [HumanMessage(content=query)],
        "query": query,
        "repo_url": repo_url or "",
        "user_id": user_id or "default_user",
        "query_analysis": {},
        "search_results": [],
        "final_answer": "",
        "domain": "",
        "iteration_count": 0,
    }

@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    """동기 방식으로 전체 답변 결과를 한 번에 반환합니다."""
    # request.message 대신 schemas.py 규격에 맞추어 request.query를 조회합니다.
    initial_state = build_initial_state(
        query=request.query,
        repo_url=request.repo_url,
        user_id=request.user_id
    )
    result = await graph.ainvoke(initial_state)
    
    # schemas.py의 ChatResponse 정의서(answer, status) 형식에 맞춰 반환합니다.
    return ChatResponse(
        answer=result.get("final_answer", ""),
        status="success"
    )

@router.post("/chat")
async def chat_stream(request: ChatRequest):
    """SSE(Server-Sent Events) 스트리밍 방식으로 에이전트의 노드 처리 과정을 실시간 전송합니다."""
    async def gen():
        initial_state = build_initial_state(
            query=request.query,
            repo_url=request.repo_url,
            user_id=request.user_id
        )
        
        async for event in graph.astream_events(initial_state, version="v2"):
            kind = event.get("event", "")
            if kind == "on_chain_end" and event.get("name") in ("analyze", "retrieve", "respond"):
                node_name = event["name"]
                node_output = event.get("data", {}).get("output", {})
                
                # StreamEvent의 data 속성 규격(Dict)에 맞게 객체 그대로 전달합니다.
                sse = StreamEvent(
                    event="node",
                    node=node_name,
                    data={"output": node_output}
                )
                yield f"data: {sse.model_dump_json()}\n\n"

        # 에이전트 연동 최종 결과 이벤트 전송
        result = await graph.ainvoke(initial_state)
        done = StreamEvent(
            event="done",
            data={
                "answer": result.get("final_answer", ""),
                "status": "success"
            }
        )
        yield f"data: {done.model_dump_json()}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")