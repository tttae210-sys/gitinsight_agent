from fastapi import APIRouter, HTTPException
from app.schemas import ChatRequest, ChatResponse, ChatResponseData, HighlightMetadata
from app.graph import create_graph
import logging

router = APIRouter()
graph = create_graph()

@router.post("/chat/sync", response_model=ChatResponse)
async def chat_sync(request: ChatRequest):
    try:
        # 1. LangGraph 스레드 설정
        config = {"configurable": {"thread_id": request.user_id}}
        
        # 2. 기존 에이전트의 내부 대화 상태 조회
        current_state = await graph.aget_state(config)
        existing_history = current_state.values.get("answer_history", []) if current_state.values else []
        
        # 3. 유저의 새 입력을 대화 기록에 누적
        new_history = list(existing_history)
        new_history.append(request.user_answer)
        
        # 4. 프론트엔드가 전송한 repo_url을 LangGraph 입력 딕셔너리에 매핑하여 강제 주입
        inputs = {
            "user_id": request.user_id,
            "repo_url": request.repo_url,  
            "answer_history": new_history,
            "retry_count": request.current_retry_count
        }
        
        # 5. 에이전트 워크플로우 동기식 실행
        final_state = await graph.ainvoke(inputs, config=config)
        
        # 6. 최종 노드 도달 상태 데이터 파싱
        next_question = final_state.get("current_question", "")
        evaluation = final_state.get("evaluation", {})
        
        feedback = evaluation.get("reason", "답변이 성공적으로 기록되었습니다.") if evaluation else "대화를 이어나갑니다."
        status = final_state.get("next_step", "PASS")
        new_retry_count = final_state.get("retry_count", request.current_retry_count)
        
        # 라인 하이라이트 데이터 파싱
        highlight_dict = final_state.get("current_highlight", None)
        highlight_meta = None
        if highlight_dict:
            highlight_meta = HighlightMetadata(
                file_path=highlight_dict.get("file_path"),
                start_line=highlight_dict.get("start_line"),
                end_line=highlight_dict.get("end_line")
            )
        
        # 7. 대시보드 세션 데이터를 빠짐없이 최종 데이터 셋에 팩킹
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