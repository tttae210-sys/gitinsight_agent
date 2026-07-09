import json
import logging
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas import ChatRequest, ChatResponse, ChatResponseData, HighlightMetadata
from app.graph import create_graph

router = APIRouter()
graph = create_graph()


# ==========================================
# 1. 동기식 면접 채점 & 대화 API
# ==========================================
@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    """
    유저의 답변을 받아 단일 동기식 응답을 반환합니다.
    이력서(resume_text)를 LangGraph State에 바인딩하여 AI 면접관이 대조 분석합니다.
    """
    try:
        # 1. LangGraph 스레드 설정
        config = {"configurable": {"thread_id": request.user_id}}

        # 2. 기존 에이전트 내부 대화 상태 조회
        current_state = await graph.aget_state(config)
        existing_history = current_state.values.get("answer_history", []) if current_state.values else []

        # 3. 유저의 새 입력을 대화 기록에 누적
        new_history = list(existing_history)
        new_history.append(request.user_answer)

        # 4. LangGraph 입력 구성 (resume_text 포함)
        inputs = {
            "user_id": request.user_id,
            "repo_url": request.repo_url,
            "resume_text": getattr(request, "resume_text", None),  # 이력서 텍스트 주입
            "answer_history": new_history,
            "retry_count": request.current_retry_count
        }

        # 5. 에이전트 워크플로우 동기식 실행
        final_state = await graph.ainvoke(inputs, config=config)

        # 6. 최종 노드 상태 파싱
        next_question = final_state.get("current_question", "")
        evaluation = final_state.get("evaluation", {})
        status = final_state.get("next_step", "PASS")
        new_retry_count = final_state.get("retry_count", request.current_retry_count)

        # 상태별 feedback 결정
        # HINT: evaluator 오답 이유를 feedback으로, extractor 힌트를 next_question으로
        if status == "HINT" and evaluation:
            feedback = evaluation.get("reason", "답변이 부족합니다. 힌트를 참고해 다시 시도해 보세요.")
        elif status in ("PASS", "FAIL") and evaluation:
            feedback = evaluation.get("reason", "")
        elif status == "REPORT":
            feedback = final_state.get("final_report", "")
        elif not evaluation and next_question:
            # 첫 질문 생성 직후 (evaluator 미실행)
            feedback = ""
        else:
            feedback = evaluation.get("reason", "") if evaluation else ""

        # 라인 하이라이트 파싱
        highlight_dict = final_state.get("current_highlight", None)
        highlight_meta = None
        if highlight_dict:
            highlight_meta = HighlightMetadata(
                file_path=highlight_dict.get("file_path"),
                start_line=highlight_dict.get("start_line"),
                end_line=highlight_dict.get("end_line")
            )

        # 7. 응답 데이터 패킹
        response_data = ChatResponseData(
            feedback=feedback,
            next_question=next_question,
            new_retry_count=new_retry_count,
            status=status,
            highlight=highlight_meta,
            tech_stack=final_state.get("tech_stack", []),
            extracted_chunks=final_state.get("extracted_chunks", []),
            evaluation=evaluation,
            final_report=final_state.get("final_report", "")
        )

        return ChatResponse(status="success", data=response_data)

    except Exception as e:
        logging.error(f"Error in chat_sync: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# ==========================================
# 2. 비동기 실시간 SSE 스트리밍 API
# ==========================================
@router.post("/chat/stream")
async def chat_stream(request: ChatRequest):
    """
    유저의 답변을 받아 LangGraph 워크플로우의 실행 현황을
    Server-Sent Events(SSE) 방식으로 실시간 중계합니다.
    """
    async def event_generator():
        try:
            config = {"configurable": {"thread_id": request.user_id}}

            current_state = await graph.aget_state(config)
            existing_history = current_state.values.get("answer_history", []) if current_state.values else []
            new_history = list(existing_history)
            new_history.append(request.user_answer)

            inputs = {
                "user_id": request.user_id,
                "repo_url": request.repo_url,
                "resume_text": getattr(request, "resume_text", None),
                "answer_history": new_history,
                "retry_count": request.current_retry_count
            }

            # 노드별 실시간 상태 메시지
            status_messages = {
                "classifier": "🎯 1단계: 지원자님의 답변 인텐트를 정밀 분류하는 중입니다...",
                "builder":    "🔍 2단계: GitHub 저장소를 추적하여 소스코드 구조를 긁어오는 중입니다...",
                "extractor":  "🧠 3단계: 코드 문맥과 이력서를 대조하여 다음 압박 질문을 생성하는 중입니다...",
                "evaluator":  "📊 4단계: 시니어 개발자 채점 엔진이 지원자님의 답변을 정밀 채점하는 중입니다...",
                "reporter":   "📝 최종단계: 면접이 완료되어 맞춤형 리팩토링 리포트를 빌드하는 중입니다...",
            }

            async for event in graph.astream(inputs, config=config, stream_mode="updates"):
                active_node = list(event.keys())[0] if event else "unknown"
                status_msg = status_messages.get(active_node, f"⚙️ {active_node} 노드가 연산을 수행 중입니다...")

                sse_data = {
                    "event": "status",
                    "node": active_node,
                    "message": status_msg
                }
                yield f"data: {json.dumps(sse_data, ensure_ascii=False)}\n\n"

            # 최종 결과 전송
            final_state = await graph.aget_state(config)
            final_values = final_state.values

            result_data = {
                "event": "result",
                "message": "채점이 성공적으로 완료되었습니다!",
                "data": {
                    "feedback": final_values.get("evaluation", {}).get("reason", ""),
                    "next_question": final_values.get("current_question", ""),
                    "new_retry_count": final_values.get("retry_count", request.current_retry_count),
                    "status": final_values.get("next_step", "PASS"),
                    "highlight": final_values.get("current_highlight", None),
                    "tech_stack": final_values.get("tech_stack", []),
                    "extracted_chunks": final_values.get("extracted_chunks", []),
                    "evaluation": final_values.get("evaluation", {}),
                    "final_report": final_values.get("final_report", "")
                }
            }
            yield f"data: {json.dumps(result_data, ensure_ascii=False)}\n\n"

        except Exception as e:
            logging.error(f"Error in SSE stream: {str(e)}")
            error_data = {"event": "error", "message": f"서버 연산 도중 예외가 발생했습니다: {str(e)}"}
            yield f"data: {json.dumps(error_data, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
