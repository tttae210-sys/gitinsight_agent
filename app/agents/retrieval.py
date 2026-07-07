import os
from langchain_core.documents import Document
from langchain_upstage import UpstageEmbeddings
from langchain_community.vectorstores import Chroma
from app.schemas import InterviewState
from app.core.config import Config

# Solar 임베딩 초기화 (모델 이름 필수 명시)
embeddings = UpstageEmbeddings(
    api_key=Config.UPSTAGE_API_KEY,
    model="solar-embedding-1-large-passage"
)

def code_build_node(state: InterviewState) -> dict:
    """
    Agent 1: CodeBuildAgent
    깃허브 주소를 받아 코드를 파싱하고 Vector DB에 캐싱/적재하는 노드.
    """
    repo_url = state.get("repo_url", "")
    commit_hash = state.get("repo_commit_hash", "")
    
    print(f"\n[DEBUG] CodeBuildAgent 가동: {repo_url} 분석 중...")
    print(f"[DEBUG] 캐시 키 검증 중... (Commit Hash: {commit_hash})")
    
    # 1. VectorDB 적재 경로 설정
    persist_dir = Config.CHROMA_DB_DIR
    
    # 2. 코드 파싱 및 Chunking (현재는 흐름 테스트를 위한 더미 데이터)
    # 실제 구현 시 PyGithub 라이브러리를 활용해 컨트롤러/서비스 로직 우선 추출
    dummy_docs = [
        Document(
            page_content="public void updateViewCount() { this.viewCount++; } // 동시성 제어 누락된 게시판 조회수 로직",
            metadata={"source": "BoardService.java", "commit": commit_hash}
        ),
        Document(
            page_content="public List<Board> getBoards() { return repository.findAll(); }",
            metadata={"source": "BoardController.java", "commit": commit_hash}
        )
    ]
    
    # 3. Upstage Solar Embedding으로 변환 및 ChromaDB에 영구 저장
    print("[DEBUG] 소스 코드 파싱 완료. Solar Embedding 변환 및 Chroma DB 적재 시작...")
    vectorstore = Chroma.from_documents(
        documents=dummy_docs,
        embedding=embeddings,
        persist_directory=persist_dir,
        collection_name="interview_cache"
    )
    print("[DEBUG] Vector DB 구축 및 캐시 적재 완료! (Cache Miss -> Build Success)")
    
    # 임시 기술 스택 추출 결과
    tech_stack = ["Java", "Spring Boot"]
    
    # 상태(State) 업데이트 후 핸드오프
    return {
        "tech_stack": tech_stack
    }

    from langchain_core.messages import SystemMessage, HumanMessage
from langchain_upstage import ChatUpstage
from app.prompts.templates import INTERVIEW_EXTRACT_PROMPT

# Solar LLM 초기화 (면접관 역할)
llm = ChatUpstage(api_key=Config.UPSTAGE_API_KEY)

def interview_extract_node(state: InterviewState) -> dict:
    """
    Agent 2: InterviewExtractAgent
    Vector DB에서 가져온 코드 청크를 바탕으로 면접 질문을 출제하는 노드.
    """
    print("\n[DEBUG] InterviewExtractAgent 가동: 압박 질문 생성 중...")
    
    # 1. State에서 필요한 데이터 꺼내기
    tech_stack = state.get("tech_stack", [])
    loop_count = state.get("loop_count", 0)
    
    # 실제 환경에서는 Chroma DB에서 retriever를 통해 유사도 검색을 수행함
    # 지금은 테스트용 더미 코드 청크를 활용
    dummy_code_chunk = "public void updateViewCount() { this.viewCount++; } // 동시성 제어 누락"
    
    # 2. 프롬프트 세팅
    messages = [
        SystemMessage(content=INTERVIEW_EXTRACT_PROMPT),
        HumanMessage(content=f"사용자 기술 스택: {tech_stack}\n코드 조각: {dummy_code_chunk}\n\n위 코드를 보고 동시성 문제와 관련된 날카로운 기술 면접 질문을 하나 던져주세요.")
    ]
    
    # 3. Solar LLM 호출하여 질문 생성
    response = llm.invoke(messages)
    question = response.content
    
    print(f"[DEBUG] 생성된 질문: {question}")
    
    # 생성된 질문을 상태에 담아서 반환
    return {
        "current_question": question
    }