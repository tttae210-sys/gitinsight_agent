"""
app/core/seed.py

서버 시작 시 ChromaDB 초기화를 관리하는 SeedManager.
- github_code_chunks 컬렉션은 GitHub 분석 요청 시 런타임에 채워진다.
- 예전 의료 QA 샘플 데이터는 GitInsight 실행 경로에서 더 이상 자동 적재하지 않는다.
"""

import logging

logger = logging.getLogger(__name__)


class SeedManager:
    """ChromaDB 초기 시드 데이터를 관리하는 클래스.

    Args:
        vector_service: 이미 초기화된 VectorService 인스턴스.
                        main.py lifespan 에서 생성한 객체를 주입받아 재사용한다.
    """

    def __init__(self, vector_service=None):
        # vector_service 는 현재 시드 로직에서 직접 사용하지 않지만,
        # 향후 코드 시드 확장 시 index_documents() 호출을 위해 보관한다.
        self._vector_service = vector_service

    def run_if_empty(self) -> None:
        """비어 있는 컬렉션에만 시드를 실행한다. (run_all 의 alias)"""
        self.run_all()

    def run_all(self) -> None:
        """등록된 모든 시드 작업을 순서대로 실행한다."""
        logger.info("[SeedManager] GitInsight는 런타임 GitHub 코드 청크를 사용하므로 기본 시드를 건너뜁니다.")
