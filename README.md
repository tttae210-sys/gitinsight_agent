# AI QA Agent API 🤖

FastAPI와 LangGraph 기반의 지능형 질의응답(QA) 에이전트 백엔드 시스템입니다. 
사용자의 질문 의도를 분석하고(`query_analyzer.py`), 필요한 경우 저장된 지식 기반에서 관련 정보를 검색(`retrieval.py`)하여, 최적의 답변을 생성(`responder.py`)하는 유연한 워크플로우를 제공합니다.

## 🧑‍💻 Contributors
- 이장혁
- 서용수
- 박태경
- 조채환

## 🚀 Tech Stack
- **Backend Framework**: FastAPI (Python)
- **AI / Workflow**: LangGraph, LangChain
- **Containerization**: Docker, Docker Compose
- **Vector Store**: (사용 중인 벡터 DB 이름 작성)

## 📦 시작하기 (Getting Started)

1. **의존성 설치**
   패키지 매니저(uv 등)를 활용하여 환경을 세팅합니다.
   ```bash
   uv sync
