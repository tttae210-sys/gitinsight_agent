import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from app.schemas import ChatRequest, ChatResponse, StreamEvent
from app.graph import create_graph

router = APIRouter()
graph = create_graph()


def build_initial_state(message: str) -> dict:
    """사용자 메시지로부터 그래프 초기 상태를 생성한다."""
    return {
        "messages": [HumanMessage(content=message)],
        "query": message,
        "query_analysis": {},
        "search_results": [],
        "final_answer": "",
        "domain": "",
        "iteration_count": 0,
    }


@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    """동기 방식으로 전체 응답을 한 번에 반환한다."""
    result = await graph.ainvoke(build_initial_state(request.message))
    return ChatResponse(answer=result.get("final_answer", ""), domain=result.get("domain", ""))


@router.post("/chat")
async def chat_stream(request: ChatRequest):
    """SSE 스트리밍으로 각 노드의 처리 과정을 실시간 전송한다."""
    async def gen():
        async for event in graph.astream_events(
            build_initial_state(request.message), version="v2"
        ):
            kind = event.get("event", "")
            if kind == "on_chain_end" and event.get("name") in ("analyze", "retrieve", "respond"):
                node_name = event["name"]
                node_output = event.get("data", {}).get("output", {})
                sse = StreamEvent(event="node", node=node_name, data=json.dumps(node_output, ensure_ascii=False, default=str))
                yield f"data: {sse.model_dump_json()}\n\n"

        # 최종 결과
        result = await graph.ainvoke(build_initial_state(request.message))
        done = StreamEvent(
            event="done",
            data=json.dumps({"answer": result.get("final_answer", ""), "domain": result.get("domain", "")}, ensure_ascii=False),
        )
        yield f"data: {done.model_dump_json()}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")
