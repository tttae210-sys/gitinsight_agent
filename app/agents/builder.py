import requests
import re
from app.schemas import InterviewState

def build_github_repo(state: InterviewState) -> dict:
    """GitHub API를 사용해 레포지토리의 소스코드를 수집하고 기술 스택을 분석합니다."""
    repo_url = state.get("repo_url", "")
    if not repo_url:
        return {"tech_stack": [], "extracted_chunks": [], "repo_commit_hash": "none"}
    
    # URL에서 유저네임과 레포지토리 이름 추출 (ex: tttae210-sys/gitinsight_agent)
    match = re.search(r"github\.com/([\w\-]+)/([\w\-]+)", repo_url)
    if not match:
        return {"tech_stack": ["Unknown"], "extracted_chunks": [], "repo_commit_hash": "none"}
    
    owner, repo = match.group(1), match.group(2)
    
    # 1. GitHub API를 통해 최신 커밋 해시 가져오기
    commit_url = f"https://api.github.com/repos/{owner}/{repo}/commits"
    commit_hash = "latest"
    try:
        commit_res = requests.get(commit_url, timeout=5).json()
        if isinstance(commit_res, list) and len(commit_res) > 0:
            commit_hash = commit_res[0].get("sha", "latest")
    except Exception:
        pass

    # 2. GitHub API를 통해 레포지토리 파일 트리 가져오기 (재귀적 탐색)
    tree_url = f"https://api.github.com/repos/{owner}/{repo}/git/trees/{commit_hash}?recursive=1"
    tech_stack = set()
    extracted_chunks = []
    
    try:
        tree_res = requests.get(tree_url, timeout=5).json()
        files = tree_res.get("tree", [])
        
        # 분석할 핵심 코드 파일 확장자 정의
        target_extensions = ('.py', '.js', '.ts', '.java', '.go', '.cpp')
        code_file_count = 0
        
        for file_info in files:
            path = file_info.get("path", "")
            # 가상환경, 패키지, 노드 모듈 폴더는 스킵 (코드 분석 오염 방지)
            if any(path.startswith(ignored) for ignored in ['.venv/', 'node_modules/', 'venv/', '.git/']):
                continue
                
            # 확장자를 보고 기술 스택 추출
            if path.endswith('.py'): tech_stack.add("Python")
            elif path.endswith(('.js', '.jsx')): tech_stack.add("JavaScript")
            elif path.endswith(('.ts', '.tsx')): tech_stack.add("TypeScript")
            elif path.endswith('.java'): tech_stack.add("Java")
            elif path.endswith('.go'): tech_stack.add("Go")
            
            # 소스코드 내용물 가져오기 (최대 3개 파일만 샘플링하여 꼬리질문용 원천 소스로 사용)
            if file_info.get("type") == "blob" and path.endswith(target_extensions) and code_file_count < 3:
                raw_url = f"https://raw.githubusercontent.com/{owner}/{repo}/{commit_hash}/{path}"
                raw_res = requests.get(raw_url, timeout=3)
                if raw_res.status_code == 200:
                    code_content = raw_res.text[:1500] # 파일당 최대 1500자 제한 (토큰 절약)
                    extracted_chunks.append({
                        "file_path": path,
                        "code": code_content,
                        "desc": f"{path} 소스코드 일부"
                    })
                    code_file_count += 1
                    
    except Exception as e:
        extracted_chunks.append({"file_path": "error", "code": str(e), "desc": "오류 발생"})

    # 기본 기술 스택 방어 로직
    if not tech_stack:
        tech_stack.add("Python (Default)")
        
    return {
        "tech_stack": list(tech_stack),
        "extracted_chunks": extracted_chunks,
        "repo_commit_hash": commit_hash
    }