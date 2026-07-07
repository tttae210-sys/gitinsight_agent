from chromadb import EmbeddingFunction
from langchain_upstage import UpstageEmbeddings


# 강의 노트북과 동일한 방식으로 임베딩 모델 생성
# api_key는 환경변수 UPSTAGE_API_KEY에서 자동으로 읽어옴
underlying_embeddings = UpstageEmbeddings(model="solar-embedding-1-large")


class UpstageChromaEmbedding(EmbeddingFunction):
    """UpstageEmbeddings를 ChromaDB EmbeddingFunction 인터페이스에 맞춘 어댑터.

    ChromaDB 1.5+는 embedding_function에 name() 메서드를 요구하므로,
    langchain의 UpstageEmbeddings를 직접 넘길 수 없어 래퍼가 필요하다.
    """

    def __call__(self, input: list[str]) -> list[list[float]]:
        return underlying_embeddings.embed_documents(input)

    @staticmethod
    def name() -> str:
        return "upstage-solar"


def get_embedding_function() -> UpstageChromaEmbedding:
    """ChromaDB 호환 Upstage 임베딩 함수를 반환한다."""
    return UpstageChromaEmbedding()
