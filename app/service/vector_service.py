"""
app/service/vector_service.py

GitHub 레포지토리에서 수집한 코드 청크를 ChromaDB에 저장하고
의미 기반으로 검색하는 서비스 레이어.

- 컬렉션명: "github_code_chunks"
- 싱글턴 패턴으로 앱 전체에서 동일 인스턴스를 재사용
"""

import uuid
from typing import Optional
from app.core.database import get_chroma_client
from app.core.embedding import get_embedding_function

COLLECTION_NAME = "github_code_chunks"

_vector_service: Optional["VectorService"] = None


class VectorService:
    def __init__(self):
        client = get_chroma_client()
        embedding_fn = get_embedding_function()
        self._collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=embedding_fn,
        )

    def index_documents(self, chunks: list[dict], metadata: dict | None = None) -> int:
        """코드 청크 리스트를 ChromaDB에 임베딩하여 저장한다.

        Args:
            chunks: builder.py 에서 생성한 extracted_chunks 리스트.
                    각 원소는 {"file_path": str, "code": str, "desc": str} 형태.
            metadata: 컬렉션에 함께 저장할 공통 메타데이터 (예: {"repo_url": "..."}).

        Returns:
            실제로 저장된 청크 수.
        """
        if not chunks:
            return 0

        base_meta = metadata or {}

        ids, documents, metadatas = [], [], []
        for chunk in chunks:
            doc_id = str(uuid.uuid4())
            file_path = chunk.get("file_path", "")
            code = chunk.get("code", "")
            desc = chunk.get("desc", "")

            # 임베딩할 텍스트: 파일 경로 + 코드 내용을 합쳐서 의미 정보를 풍부하게
            document_text = f"[파일: {file_path}]\n{code}"

            ids.append(doc_id)
            documents.append(document_text)
            metadatas.append({
                **base_meta,
                "file_path": file_path,
                "desc": desc,
            })

        self._collection.add(ids=ids, documents=documents, metadatas=metadatas)
        return len(ids)

    def has_documents(self, filters: dict) -> bool:
        """주어진 메타데이터 조건에 맞는 문서가 이미 적재되어 있는지 확인한다."""
        if self._collection.count() == 0:
            return False

        try:
            result = self._collection.get(where=filters, limit=1)
        except Exception:
            return False

        return bool(result.get("ids"))

    def search(
        self,
        query: str,
        filters: dict | None = None,
        n_results: int = 3,
    ) -> list[dict]:
        """쿼리와 의미적으로 가까운 코드 청크를 검색한다.

        Args:
            query: 검색할 자연어 질문 또는 키워드.
            filters: ChromaDB where 조건 (예: {"repo_url": "https://github.com/..."}).
                     None 이면 전체 컬렉션에서 검색.
            n_results: 반환할 최대 결과 수 (기본 3개).

        Returns:
            [{"file_path": str, "content": str, "distance": float}, ...] 형태의 리스트.
        """
        if self._collection.count() == 0:
            return []

        try:
            results = self._collection.query(
                query_texts=[query],
                n_results=n_results,
                where=filters if filters else None,
            )
        except Exception:
            # where 필터에 해당하는 문서가 0개일 때 chromadb가 예외를 던질 수 있음
            return []

        output = []
        if results and results.get("documents"):
            docs = results["documents"][0]
            metas = results.get("metadatas", [[]])[0]
            dists = results.get("distances", [[]])[0]
            for i, doc in enumerate(docs):
                output.append({
                    "file_path": metas[i].get("file_path", "") if metas else "",
                    "content": doc,
                    "distance": dists[i] if dists else None,
                })
        return output


def get_vector_service() -> VectorService:
    """앱 전체에서 공유하는 VectorService 싱글턴을 반환한다."""
    global _vector_service
    if _vector_service is None:
        _vector_service = VectorService()
    return _vector_service
