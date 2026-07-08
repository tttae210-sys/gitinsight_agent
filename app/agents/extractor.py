from typing import Optional
from pydantic import BaseModel, Field
from app.schemas import InterviewState
from langchain_core.prompts import ChatPromptTemplate
from app.core.llm import get_llm

class ExtractedQuestionSchema(BaseModel):
    question: str = Field(description="지원자에게 던질 구체적인 꼬리 질문")
    file_path: Optional[str] = Field(None, description="질문 중 언급하거나 지적한 소스코드의 파일 경로")
    start_line: Optional[int] = Field(None, description="지적한 코드 영역의 시작 줄 번호 (1부터 시작)")
    end_line: Optional[int] = Field(None, description="지적한 코드 영역의 끝 줄 번호 (1부터 시작)")

def extract_interview_question(state: InterviewState) -> dict:
    """수집된 소스코드 문맥에 라인 번호를 명시하고, LLM을 통해 질문과 하이라이트 메타데이터를 함께 추출합니다."""
    llm = get_llm(temperature=0.4)
    structured_llm = llm.with_structured_output(ExtractedQuestionSchema)
    
    tech_stack = ", ".join(state.get("tech_stack", []))
    loop_count = state.get("loop_count", 0)
    chunks = state.get("extracted_chunks", [])
    
    code_context = ""
    for chunk in chunks:
        file_path = chunk.get('file_path')
        code_context += f"--- File: {file_path} ---\n"
        
        lines = chunk.get('content', '').split('\n')
        for idx, line in enumerate(lines, 1):
            code_context += f"{idx}: {line}\n"
        code_context += "\n"
        
    if not code_context:
        code_context = "제출된 소스코드에 분석 가능한 주요 코드 파일이 존재하지 않습니다."

    # 🔴 [버그 수정 1] f-string 대신 LangChain의 고유 변수 {code_context}로 뚫어놓습니다.
    system_msg = (
        "당신은 강원대학교 컴퓨터공학과 학생들을 위해 기술 면접을 진행하는 IT 대기업의 시니어 면접관입니다.\n"
        f"지원자의 기술 스택({tech_stack})과 소스코드 문맥을 철저히 분석하여 전공자 수준의 날카로운 꼬리 질문을 던지세요.\n\n"
        "[프로젝트 소스코드 문맥 (줄번호 포함)]\n"
        "{code_context}\n\n"
        "지침:\n"
        "1. 질문 내용과 연관이 깊은 코드 조각이 있다면, 해당 파일의 파일 경로와 시작 줄 번호(start_line), 끝 줄 번호(end_line)를 정확히 지정해 주세요.\n"
        "2. 반드시 위에 명시된 소스코드 문맥의 '실제 줄 번호'와 일치하게 지정해야 합니다. 소스코드 범위를 벗어나거나 엉뚱한 줄 번호를 적어서는 안 됩니다.\n"
        "3. 만약 특정 소스코드를 지목할 필요가 없는 일반 CS 꼬리 질문인 경우, file_path, start_line, end_line은 null(None)로 반환하세요.\n"
        "4. 한 번에 딱 한 가지 질문만 명확히 던지세요."
    )
    
    answer_history = state.get("answer_history", [])
    history_conversation = ""
    for idx, chat in enumerate(answer_history):
        role = "지원자" if idx % 2 != 0 else "면접관"
        history_conversation += f"- {role}: {chat}\n"
    
    # 🔴 [버그 수정 2] human 프롬프트 역시 f-string을 제거하고 {history_conversation} 변수로 받습니다.
    prompt = ChatPromptTemplate.from_messages([
        ("system", system_msg),
        ("human", "이전 면접 대화 기록:\n{history_conversation}\n\n위 문맥을 이어받아 다음 면접 질문과 하이라이트 영역을 구성해 주세요.")
    ])
    
    chain = prompt | structured_llm
    
    # 🔴 [버그 수정 3] 텅 빈 딕셔너리({}) 대신, 방금 뚫어놓은 변수들의 실제 텍스트 데이터를 안전하게 주입(invoke)합니다.
    response = chain.invoke({
        "code_context": code_context,
        "history_conversation": history_conversation
    })
    
    highlight_data = {
        "file_path": response.file_path,
        "start_line": response.start_line,
        "end_line": response.end_line
    } if response.file_path else None

    return {
        "current_question": response.question,
        "current_highlight": highlight_data, 
        "loop_count": loop_count + 1
    }