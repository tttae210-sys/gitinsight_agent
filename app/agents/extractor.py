from app.schemas import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm

def extract_interview_question(state: InterviewState) -> dict:
    """수집된 소스코드 문맥과 답변 히스토리를 바탕으로 맞춤형 기술 면접 질문을 생성합니다."""
    llm = get_llm(temperature=0.7) # 질문의 다양성을 위해 온도를 살짝 올림
    
    # 상태값 꺼내기
    tech_stack = ", ".join(state.get("tech_stack", []))
    loop_count = state.get("loop_count", 0)
    chunks = state.get("extracted_chunks", [])
    
    # 깃허브에서 가져온 소스코드 문맥 병합
    code_context = ""
    for chunk in chunks:
        code_context += f"--- File: {chunk.get('file_path')} ---\n{chunk.get('code')}\n\n"
    if not code_context:
        code_context = "제출된 소스코드에 분석 가능한 파이썬 또는 주요 코드 파일이 존재하지 않습니다."

    # 면접관 페르소나 및 지침 하드코딩 (이해하기 쉽게 한 번에 하나씩 질문)
    system_msg = (
        "당신은 강원대학교 컴퓨터공학과 학생들을 위해 기술 면접을 진행하는 아주 정교하고 날카로운 IT 대기업의 시니어 면접관 선배입니다.\n"
        f"지원자의 기술 스택({tech_stack})과 그들이 직접 작성한 아래 [프로젝트 소스코드 문맥]을 철저히 분석하여 전공자 수준의 질문을 던지세요.\n\n"
        "[프로젝트 소스코드 문맥]\n"
        f"{code_context}\n\n"
        "지침:\n"
        "1. 절대 추상적인 질문을 하지 말고, 위 소스코드에서 유저가 사용한 라이브러리, 함수 구조, 자료구조, 예외 처리 방식 등 '진짜 코드 기반'의 꼬리 질문을 던지세요.\n"
        f"2. 현재 질문 회차는 {loop_count + 1}회차입니다. (최대 3회 진행 예정)\n"
        "3. 만약 이전 답변 히스토리가 있다면, 유저가 한 답변의 허점을 찌르거나 더 깊은 CS 지식(메모리 관리, 시간복잡도 등)을 물어보는 꼬리 질문을 던지세요.\n"
        "4. 전공생이 이해하기 쉽도록 문맥을 잘 정리하고, 반드시 '한 번에 딱 한 가지 질문만' 던지세요."
    )
    
    # 대화 히스토리 구성
    answer_history = state.get("answer_history", [])
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", f"이전 면접 대화 기록: {answer_history}\n\n위 문맥을 이어받아 다음 면접 질문을 하나만 생성해 주세요.")
    ])
    
    chain = prompt | llm
    response = chain.invoke({})
    
    return {
        "current_question": response.content.strip(),
        "loop_count": loop_count + 1
    }