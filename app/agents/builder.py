import os
import requests
import re
import logging
import chromadb
from app.schemas import InterviewState

# ==========================================
# 0. 안전 임포트 처리
# ==========================================
try:
    from app.service.vector_service import get_vector_service
except ImportError:
    get_vector_service = None


# ==========================================
# 1. 런타임 크로스 플랫폼 임베딩 어댑터
# ==========================================
class LangChainEmbeddingAdapter:
    """
    LangChain Embeddings 객체를 ChromaDB가 이해할 수 있는
    임베딩 함수 규격으로 변환해 주는 어댑터 클래스입니다.
    """
    def __init__(self, lc_embeddings):
        self.lc_embeddings = lc_embeddings

    def __call__(self, input: list) -> list:
        return self.lc_embeddings.embed_documents(input)


# ==========================================
# 2. 동적 DB 클라이언트 & 임베딩 추출기
# ==========================================
def extract_active_db_resources() -> tuple:
    """
    기존에 메모리에 기동 중인 VectorService로부터
    Chroma Client와 Embedding Function을 추출합니다.
    """
    if not get_vector_service:
        return None, None

    try:
        vector_service = get_vector_service()
        chroma_client = None
        embedding_fn = None

        # [A] ChromaDB 클라이언트 동적 추출
        for attr_name in ["_client", "client", "chroma_client", "_chroma_client"]:
            if hasattr(vector_service, attr_name):
                val = getattr(vector_service, attr_name)
                if val.__class__.__name__ in ["Client", "PersistentClient", "API", "HttpClient"]:
                    chroma_client = val
                    break

        if not chroma_client:
            for attr_name in dir(vector_service):
                try:
                    val = getattr(vector_service, attr_name)
                    if val.__class__.__name__ in ["Client", "PersistentClient", "API", "HttpClient"]:
                        chroma_client = val
                        break
                except Exception:
                    continue

        # [B] LangChain 임베딩 모델 추출 및 어댑터 래핑
        for attr_name in ["_embedding_function", "embeddings", "embedding_function", "_embeddings"]:
            if hasattr(vector_service, attr_name):
                val = getattr(vector_service, attr_name)
                if hasattr(val, "embed_query") and hasattr(val, "embed_documents"):
                    embedding_fn = LangChainEmbeddingAdapter(val)
                    logging.info("🎯 [ChromaDB] 기존 설정된 임베딩 함수를 어댑터로 자동 변환했습니다.")
                    break

        return chroma_client, embedding_fn

    except Exception as e:
        logging.error(f"Failed to dynamically inspect VectorService: {str(e)}")
        return None, None


# ==========================================
# 3. GitHub 빌더 에이전트 핵심 비즈니스 로직
# ==========================================
def build_github_repo(state: InterviewState) -> dict:
    """
    GitHub API를 사용해 레포지토리의 소스코드를 수집하고 기술 스택을 분석합니다.
    기존 ChromaDB 커넥션을 재사용해 SQLite Lock 및 타임아웃을 방지합니다.
    """
    repo_url = state.get("repo_url", "")
    if not repo_url:
        return {"tech_stack": [], "extracted_chunks": [], "repo_commit_hash": "none"}

    match = re.search(r"github\.com/([\w\-]+)/([\w\-\.]+)", repo_url)
    if not match:
        return {"tech_stack": ["Unknown"], "extracted_chunks": [], "repo_commit_hash": "none"}

    owner, repo = match.group(1), match.group(2)

    headers = {}
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        headers["Authorization"] = f"token {github_token}"

    # 1. 최신 커밋 해시 가져오기
    commit_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    commit_hash = "latest"
    try:
        commit_res = requests.get(commit_url, headers=headers, timeout=5)
        if commit_res.status_code == 200:
            commit_data = commit_res.json()
            if isinstance(commit_data, list) and len(commit_data) > 0:
                commit_hash = commit_data[0].get("sha", "latest")
    except Exception as e:
        logging.error(f"GitHub Commit API Error: {str(e)}")

    # Chroma 컬렉션 네이밍 규칙 준수
    safe_repo_name = re.sub(r"[^a-zA-Z0-9_\-]", "_", repo)[:20]
    collection_name = f"repo-{owner}-{safe_repo_name}-{commit_hash[:10]}".lower()

    tech_stack = set()
    extracted_chunks = []

    try:
        chroma_client, embedding_fn = extract_active_db_resources()

        if chroma_client is None:
            logging.warning("⚠️ 활성화된 VectorService를 찾지 못해 백업 클라이언트를 생성합니다.")
            chroma_client = chromadb.PersistentClient(path="./chroma_data")

        existing_collections = [c.name for c in chroma_client.list_collections()]

        # 2. [Cache Hit]: 동일 커밋 캐시가 이미 존재하면 DB에서 복원
        if collection_name in existing_collections:
            logging.info(f"⚡ [Cache Hit] 커밋 캐시 발견! (Commit: {commit_hash[:7]})")

            if embedding_fn:
                collection = chroma_client.get_collection(name=collection_name, embedding_function=embedding_fn)
            else:
                collection = chroma_client.get_collection(name=collection_name)

            results = collection.get()

            for doc, metadata in zip(results.get("documents", []), results.get("metadatas", [])):
                extracted_chunks.append({
                    "file_path": metadata.get("file_path", "unknown"),
                    "content": doc,
                    "code": doc,
                    "desc": metadata.get("desc", "")
                })
                lang = metadata.get("language", "")
                if lang:
                    tech_stack.add(lang)

            return {
                "tech_stack": list(tech_stack) if tech_stack else ["Python (Cached)"],
                "extracted_chunks": extracted_chunks,
                "repo_commit_hash": commit_hash
            }

        # 3. [Cache Miss]: 신규 다운로드 및 임베딩 분석
        logging.info(f"🛰️ [Cache Miss] 신규 코드 변경 감지. 깃허브 트리 분석 시작 (SHA: {commit_hash[:7]})")
        tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{commit_hash}?recursive=1"
        tree_res = requests.get(tree_url, headers=headers, timeout=5).json()
        files = tree_res.get("tree", [])

        target_extensions = ('.py', '.js', '.ts', '.java', '.go', '.cpp')
        code_file_count = 0
        documents_to_embed = []
        metadatas_to_embed = []
        ids_to_embed = []

        for file_info in files:
            path = file_info.get("path", "")
            if any(path.startswith(ignored) for ignored in ['.venv/', 'node_modules/', 'venv/', '.git/', '__pycache__/']):
                continue

            current_lang = ""
            if path.endswith('.py'): current_lang = "Python"
            elif path.endswith(('.js', '.jsx')): current_lang = "JavaScript"
            elif path.endswith(('.ts', '.tsx')): current_lang = "TypeScript"
            elif path.endswith('.java'): current_lang = "Java"
            elif path.endswith('.go'): current_lang = "Go"

            if current_lang:
                tech_stack.add(current_lang)

            if file_info.get("type") == "blob" and path.endswith(target_extensions) and code_file_count < 3:
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit_hash}/{path}"
                raw_res = requests.get(raw_url, timeout=3)
                if raw_res.status_code == 200:
                    code_content = raw_res.text[:1500]

                    extracted_chunks.append({
                        "file_path": path,
                        "content": code_content,
                        "code": code_content,
                        "desc": f"{path} 소스코드 일부"
                    })

                    documents_to_embed.append(code_content)
                    metadatas_to_embed.append({
                        "file_path": path,
                        "language": current_lang or "Other",
                        "desc": f"{path} 소스코드 일부"
                    })
                    ids_to_embed.append(f"chunk_{code_file_count}")
                    code_file_count += 1

        # 4. 수집된 코드를 ChromaDB에 저장
        if documents_to_embed:
            if embedding_fn:
                new_collection = chroma_client.get_or_create_collection(name=collection_name, embedding_function=embedding_fn)
            else:
                new_collection = chroma_client.get_or_create_collection(name=collection_name)

            new_collection.add(
                documents=documents_to_embed,
                metadatas=metadatas_to_embed,
                ids=ids_to_embed
            )
            logging.info(f"💾 [ChromaDB] 컬렉션 '{collection_name}' 저장 성공!")

    except Exception as e:
        logging.error(f"Builder Agent Runtime Exception: {str(e)}")
        extracted_chunks.append({
            "file_path": "README.md",
            "content": "프로젝트 분석 시스템 초기 세팅이 완료되었습니다. 프로젝트의 기능 및 아키텍처에 대한 면접을 시작합니다.",
            "code": "",
            "desc": "기본 컨텍스트"
        })

    if not tech_stack:
        tech_stack.add("Python (Default)")

    return {
        "tech_stack": list(tech_stack),
        "extracted_chunks": extracted_chunks,
        "repo_commit_hash": commit_hash
    }
