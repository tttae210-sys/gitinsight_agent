import json
import logging
import traceback
from fastapi import APIRouter, HTTPException
from fastapi.responses import StreamingResponse
from app.schemas import ChatRequest, ChatResponse, ChatResponseData, HighlightMetadata, ResetRequest
from app.graph import create_graph

router = APIRouter()
graph = create_graph()


# ==========================================
# 0. 면접 기록 초기화 API
# ==========================================
@router.post("/chat/reset")
async def chat_reset(request: ResetRequest):
    """
    LangGraph MemorySaver에 저장된 해당 유저의 스레드 상태를 완전히 초기화합니다.
    프론트엔드 '면접 기록 초기화' 버튼과 연동됩니다.
    """
    try:
        config = {"configurable": {"thread_id": request.user_id}}
        # 빈 상태로 덮어써서 이전 체크포인트를 무효화
        await graph.aupdate_state(config, {
            "answer_history":    [],
            "current_question":  "",
            "question_pool":     [],  # 🔴 이전 질문 풀 완전 제거
            "extracted_chunks":  [],
            "tech_stack":        [],
            "evaluation":        {},
            "final_report":      "",
            "retry_count":       0,
            "loop_count":        0,
            "next_step":         "",
            "current_highlight": None,
            "repo_url":          None,  # 🔴 레포 URL도 초기화
            "resume_text":       None,  # 🔴 이력서도 초기화
            "repo_commit_hash":  None,  # 🔴 커밋 해시도 초기화
        })
        return {"status": "ok", "message": f"{request.user_id} 스레드 초기화 완료"}
    except Exception as e:
        logging.error(f"Error in chat_reset: {str(e)}\n{traceback.format_exc()}")
        raise HTTPException(status_code=500, detail=str(e))


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
        if status == "ANSWER_GIVEN" and evaluation:
            feedback = evaluation.get("reason", "")
        elif status in ("HINT", "HINT_GIVEN", "SURRENDER") and evaluation:
            # 🔴 힌트는 current_question에 이미 포함되어 있으므로 feedback 비우기
            feedback = ""
        elif status in ("PASS", "FAIL") and evaluation:
            feedback = evaluation.get("reason", "")
        elif status == "REPORT":
            feedback = final_state.get("final_report", "")
        elif not evaluation and next_question:
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
        logging.error(f"Error in chat_sync: {str(e)}\n{traceback.format_exc()}")
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
                # ── 전처리 에이전트 ──────────────────────────────────────────
                "classifier":         "🎯 입력 분석 중: 지원자님의 의도를 파악하고 있습니다...",
                "builder":            "🔍 코드 수집 중: GitHub 저장소에서 소스코드를 가져오는 중입니다...",
                "question_extractor": "🧠 질문 생성 중: 소스코드와 이력서를 분석해 면접 질문 풀을 사전 생성하는 중입니다...",
                # ── 실시간 인터랙션 에이전트 ─────────────────────────────────
                "evaluator":          "📊 채점 중: 시니어 면접관이 지원자님의 답변을 정밀 평가하는 중입니다...",
                "hint_agent":         "💡 힌트 생성 중: 소스코드에서 단서를 찾아 힌트를 준비하는 중입니다...",
                "answer_provider":    "📖 모범 답안 생성 중: 핵심 개념과 코드 기반 해설을 작성하는 중입니다...",
                "next_question":      "➡️ 다음 질문 준비 중: 질문 풀에서 다음 면접 질문을 꺼내는 중입니다...",
                "reporter":           "📝 리포트 생성 중: 전체 면접 결과를 종합하여 맞춤형 피드백 리포트를 작성하는 중입니다...",
                "chat":               "💬 안내 메시지를 준비하는 중입니다...",
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
