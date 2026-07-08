import json
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from app.schemas import ChatRequest, ChatResponse, ChatResponseData, StreamEvent, InterviewState
from app.graph import create_graph

router = APIRouter()
graph = create_graph()

def build_initial_state(request: ChatRequest) -> InterviewState:
    """API 요청을 LangGraph 공통 상태로 변환한다."""
    user_input = request.message or request.query
    history = list(request.answer_history or [])
    if not history or history[-1] != user_input:
        history.append(user_input)

    return InterviewState(
        user_id=request.user_id,
        repo_url=request.repo_url or "",
        repo_commit_hash="",
        tech_stack=[],
        extracted_chunks=[],
        current_question=request.current_question,
        answer_history=history,
        loop_count=request.current_retry_count,
        evaluation=None,
        final_report=None,
        next_step="ANSWER" if request.current_question else "START",
    )

@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    """동기 방식으로 전체 응답을 한 번에 반환한다."""
    state = build_initial_state(request)
    result = await graph.ainvoke(state)
    eval_data = result.get("evaluation") or {}
    final_report = result.get("final_report") or ""
    next_question = result.get("current_question") or ""
    status = _response_status(eval_data, final_report, next_question)
    
    return ChatResponse(
        status="success",
        data=_build_response_data(result, status)
    )

@router.post("/chat")
async def chat_stream(request: ChatRequest):
    """SSE 스트리밍으로 각 노드의 처리 과정 실시간 전송"""
    state = build_initial_state(request)
    
    async def gen():
        final_state = state
        async for event in graph.astream_events(state, version="v2"):
            kind = event.get("event", "")
            if kind == "on_chain_end" and event.get("name") in (
                "intent_classifier",
                "code_build",
                "interview_extract",
                "evaluation",
                "feedback_gen",
            ):
                node_name = event["name"]
                node_output = event.get("data", {}).get("output", {})
                if isinstance(node_output, dict):
                    final_state = {**final_state, **node_output}

                sse = StreamEvent(
                    event="node", 
                    node=node_name, 
                    data=json.dumps(node_output, ensure_ascii=False, default=str)
                )
                yield f"data: {sse.model_dump_json()}\n\n"

        if final_state:
            done_data = _build_response_data(final_state).model_dump()
            done = StreamEvent(
                event="done",
                data=json.dumps(done_data, ensure_ascii=False),
            )
            yield f"data: {done.model_dump_json()}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


def _response_status(eval_data: dict, final_report: str, next_question: str) -> str:
    if final_report:
        return "REPORT"
    if eval_data.get("status") == "PASS":
        return "PASS"
    if eval_data.get("status") == "FAIL":
        return "HINT"
    if next_question:
        return "QUESTION"
    return "CHAT"


def _build_response_data(result: dict, status: str | None = None) -> ChatResponseData:
    eval_data = result.get("evaluation") or {}
    final_report = result.get("final_report") or ""
    next_question = result.get("current_question") or ""
    resolved_status = status or _response_status(eval_data, final_report, next_question)
    answer = final_report or next_question or eval_data.get("hint") or eval_data.get("reason") or ""

    return ChatResponseData(
        evaluation_score=int(eval_data.get("score", 0) or 0),
        feedback=eval_data.get("reason", ""),
        is_finished=bool(final_report or eval_data.get("status") == "PASS"),
        next_question=next_question,
        answer=answer,
        status=resolved_status,
        new_retry_count=int(result.get("loop_count", 0) or 0),
        tech_stack=result.get("tech_stack", []) or [],
        extracted_chunks=result.get("extracted_chunks", []) or [],
        final_report=final_report,
    )
