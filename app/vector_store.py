from app.service.vector_service import get_vector_service


def seed_if_empty():
    """GitInsight 코드 청크는 GitHub 분석 요청 시 적재되므로 기본 시드는 없다."""
    return None


def search_documents(
    query: str,
    n_results: int = 3,
    repo_url: str | None = None,
    commit_hash: str | None = None,
) -> list[dict]:
    """기존 import 호환성을 유지하는 GitHub 코드 청크 검색 래퍼."""
    filters = None
    if repo_url and commit_hash:
        filters = {"$and": [{"repo_url": repo_url}, {"commit_hash": commit_hash}]}
    elif repo_url:
        filters = {"repo_url": repo_url}

    return get_vector_service().search(query=query, filters=filters, n_results=n_results)
