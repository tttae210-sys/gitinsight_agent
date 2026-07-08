# GitInsight Agent

GitHub 레포지토리의 핵심 소스 코드를 수집하고, RAG 기반 문맥으로 기술 면접 질문과 답변 피드백을 생성하는 FastAPI + LangGraph 프로젝트입니다.

## 주요 기능

- GitHub Repository URL 감지 및 분석 워크플로우 트리거
- 최신 commit hash 기준 코드 청크 캐싱
- ChromaDB 기반 코드 청크 검색
- 코드 문맥 기반 기술 면접 질문 생성
- 사용자 답변 평가, 최대 3회 튜터링 루프, 최종 피드백 리포트 생성
- Streamlit 기반 모의 면접 UI

## Tech Stack

- Backend: FastAPI
- Agent Workflow: LangGraph, LangChain
- LLM/Embedding: Upstage Solar
- Vector Store: ChromaDB
- Frontend: Streamlit
- Runtime/Package Manager: uv

## 실행 방법

1. `.env` 파일에 `UPSTAGE_API_KEY`를 설정합니다.
2. 로컬 실행:

```bash
./start.sh
```

3. 접속 주소:

- Backend: http://localhost:8000
- Frontend: http://localhost:8501

## Docker Compose

```bash
docker compose up --build
```

Frontend 컨테이너는 `API_BASE_URL=http://api:8000/api/v1`로 백엔드 API를 호출합니다.
