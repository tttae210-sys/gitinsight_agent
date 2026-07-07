from app.state import InterviewState

def build_github_repo(state: InterviewState) -> dict:
    repo_url = state.get("repo_url", "")
    
    mock_tech_stack = ["Python", "LangChain"]
    mock_chunks = [{"code": "print('hello')", "desc": "메인 함수"}]
    
    return {
        "tech_stack": mock_tech_stack,
        "extracted_chunks": mock_chunks,
        "repo_commit_hash": "latest_hash_123"
    }