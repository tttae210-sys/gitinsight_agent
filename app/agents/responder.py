import json
from langchain_core.messages import SystemMessage, HumanMessage
from langchain_upstage import ChatUpstage
# 💡 graph.py와 맞춰서 schemas 구조 그대로 유지
from app.schemas import InterviewState
from app.prompts.templates import EVALUATOR_PROMPT, FEEDBACK_GEN_PROMPT
from app.core.config import Config

# Solar LLM 초기화
llm = ChatUpstage(api_key=Config.UPSTAGE_API_KEY)

def evaluation_node(state: InterviewState) -> dict:
    """
    유저의 답변이 기준(루브릭)을 충족하는지 평가하는 핵심 블랙박스 노드.
    """
    current_question = state.get("current_question", "")
    answer_history = state.get("answer_history", [])
    loop_count = state.get("loop_count", 0)
    
    # 방금 유저가 입력한 최신 답변 가져오기
    user_answer = answer_history[-1] if answer_history else ""
    
    print(f"\n[DEBUG] 유저 답변 평가 중... (현재 Loop: {loop_count} / {Config.MAX_LOOP_COUNT})")
    
    # 평가 프롬프트에 질문과 유저 답변 맵핑
    eval_prompt = EVALUATOR_PROMPT.format(
        current_question=current_question, 
        user_answer=user_answer
    )
    
    # Solar LLM 호출
    response = llm.invoke([SystemMessage(content=eval_prompt)])
    
    # LLM이 뱉은 JSON 텍스트 파싱 (마크다운 백틱 제거 등 안전장치)
    try:
        content = response.content.strip().replace("```json", "").replace("```", "").strip()
        eval_result = json.loads(content)
    except json.JSONDecodeError:
        print("[DEBUG] JSON 파싱 에러 발생, 기본값으로 대체합니다.")
        eval_result = {
            "status": "FAIL", 
            "score": 0,
            "is_satisfied": False,
            "reason": "응답 포맷 오류", 
            "hint": "답변을 조금 더 구체적인 기술 키워드를 포함해서 다시 설명해주시겠어요?"
        }

    eval_result.setdefault("score", 10 if eval_result.get("status") == "PASS" else 0)
    eval_result.setdefault("is_satisfied", eval_result.get("status") == "PASS")
        
    print(f"[DEBUG] 평가 결과: {eval_result['status']} | 사유: {eval_result.get('reason', '')}")
    
    # 💥 버그 수정: loop_count + 1을 제거했습니다! 
    # 카운트 증가는 extractor.py에서 전담하므로 여기서는 평가 결과만 쏙 업데이트합니다.
    return {
        "evaluation": eval_result
    }

def feedback_gen_node(state: InterviewState) -> dict:
    """
    Agent 3: FeedbackGenAgent
    면접이 종료된 후 (루프 3회 도달 or 정답 PASS 시) 최종 피드백 리포트를 생성하는 노드.
    """
    print("\n[DEBUG] FeedbackGenAgent 가동: 최종 리포트 생성 중...")
    
    answer_history = state.get("answer_history", [])
    
    messages = [
        SystemMessage(content=FEEDBACK_GEN_PROMPT),
        HumanMessage(content=f"면접 기록:\n{answer_history}")
    ]
    
    response = llm.invoke(messages)
    
    print("[DEBUG] 최종 피드백 리포트 생성 완료!")
    
    return {
        "final_report": response.content
    }
