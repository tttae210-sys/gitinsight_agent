🤖 GitInsight Agent

GitHub 소스코드 분석 및 이력서 교차 검증 기반 AI 모의 기술면접 에이전트

📌 1. 프로젝트 개요 (Introduction)

GitInsight Agent는 지원자의 이력서(주장, Claim)와 실제 GitHub 저장소의 소스코드(증거, Proof)를 실시간으로 교차 분석하여, 단순 암기 위주의 기술 면접을 탈피하고 실무 역량을 팩트 기반으로 정밀 검증하는 AI 모의면접 플랫폼입니다.

기존의 획일적인 모의면접 서비스와 달리, LangGraph 멀티 에이전트 아키텍처를 기반으로 지원자의 대답 품질에 맞추어 실시간 적응형 난이도 제어(Easy ➡️ Normal ➡️ Hard) 및 3-Strike 소크라테스식 코드 하이라이팅 힌트 시스템을 제공하여 수준 높은 맞춤형 기술 면접 경험을 제공합니다.

🏛️ 2. 서비스 아키텍처 (System Architecture)

GitInsight는 컴포넌트 간 단일 책임 원칙(SRP)과 격리성을 확보한 비동기 마이크로서비스 아키텍처를 지향합니다.

       ┌────────────────────────┐
       │   Streamlit Frontend   │ <─── (User UUID Session Isolation)
       └───────────┬────────────┘
                   │ 
                   │ (HTTP REST API / JSON 통신)
                   ▼
       ┌────────────────────────┐
       │    FastAPI Backend     │
       └───────────┬────────────┘
                   │
         ┌─────────┴─────────┐
         ▼                   ▼
┌─────────────────┐ ┌────────────────────────────────────────────────────────┐
│  Vector DB      │ │  LangGraph Stateful Agent Workflow                     │
│  (ChromaDB)     │ │                                                        │
│                 │ │               ┌── [START] ──> builder                  │
│ - Commit-Hash   │ │               │                  │                     │
│   Caching       │ │               │                  ▼                     │
│ - Upstage Solar │ │  classifier ──┼── [ANSWER] ─> evaluator (Score Scale)  │
│   Embedding     │ │               │                  │                     │
│                 │ │               │                  ├─ [PASS] -> next_q   │
│                 │ │               │                  ├─ [HINT] -> hint_ag  │
│                 │ │               │                  └─ [FAIL] -> reporter │
│                 │ │               └── [CHAT] ───> chat                     │
└─────────────────┘ └────────────────────────────────────────────────────────┘


🚀 3. 핵심 킬러 기능 (Killer Features)

🎯 ① 듀얼 LLM 기반 동적 라우팅 (Dynamic Workflow Branching)

교육원(OT) 지침에 명시된 "LLM 직접 판단 기반의 분기 로직"을 시스템 아키텍처 내에 듀얼(Dual) 구조로 설계 및 구현했습니다.

의도 판별 동적 라우팅 (classifier): 유저의 입력을 단순히 if-else 키워드로 매칭하는 한계를 넘어서, LLM이 문맥의 성격을 파악하여 기술 답변(ANSWER)과 일상 대화(CHAT)를 스스로 분별해 경로를 결정합니다.

채점 정합성 기반 상태 전이 (evaluator): 소스코드 문맥과 지원자의 답변을 LLM이 종합 채점하여 PASS(다음 질문), HINT(노란 형광펜 힌트 제공), FAIL(3-Strike 성적표 발행)의 후속 라이프사이클 분기를 유기적으로 트리거합니다.

⚡ ② 실시간 난이도 조절 및 동적 질문 브랜칭 (Dynamic Difficulty Scaling)

지원자가 고품질의 답변(8점 이상)을 제출하면, LLM 면접관이 이를 인지하고 다음 질문의 난이도를 HARD로 자동 격상하여 동시성 스레드 동기화, 메모리 GC 누수, 인프라 트레이드오프 등 시니어 수준의 질문을 던집니다.

답변이 부족하여 HINT 상태에 머무는 동안에는 기존 질문의 난이도를 고정(Freeze)하여 시각적 혼선을 예방하고, 최종 통과 시에만 난이도가 스케일링되는 정교한 상태 조율 알고리즘을 적용했습니다.

⚾ ③ 3-Strike 힌트 루프 & Yellow Marker 코드 하이라이팅

지원자가 기술적 설명에 정답을 제시하지 못하거나 모르겠다고 할 경우, 정답을 직접 노출하지 않고 해당 깃허브 소스코드의 구체적인 라인 범위를 노란색 형광펜으로 짚어주며(Highlighting) 스스로 정답의 실마리를 유추하도록 유도하는 소크라테스식 튜터링을 제공합니다.

📊 ④ 이력서(Claim) - 깃허브(Proof) 교차 검증 및 레포트

이력서 업로드(pypdf 기반 동적 파싱) 시, 이력서에 가득 찬 성과 포장의 거품을 실제 구현 소스코드로 교차 검증하여 허점과 기술적 타당성을 파고듭니다.

면접 종료 시, 시니어 멘토 사적 서명 원천 배제 가이드가 탑재된 정제된 1:1 맞춤형 피드백 마크다운 보고서(reporter)를 생성하여 제공합니다.

🛠️ 4. 기술 스택 및 아키텍처 결정 이유 (Tech Stack)

⚙️ Backend & Frontend

FastAPI (ASGI, Async): 다수의 LLM API 호출 및 벡터 DB RAG 쿼리로 인해 발생하는 대기 시간(I/O Bound) 병목을 비동기 루틴으로 해소하고, Pydantic을 코어로 탑재하여 통신 객체의 완벽한 데이터 정합성을 보장합니다.

Streamlit: 파이썬 환경의 가벼운 프로토타입 환경이지만, st.session_state 및 st.rerun()의 정교한 매핑 동기화를 통해 복잡한 세션 상태 전이를 지연 시간 없이 화면에 실시간 바인딩합니다.

🧠 Model & Database

Upstage Solar-pro2 LLM: 뛰어난 한국어 이해력과 빠른 응답 속도를 바탕으로 날카로운 기술 면접관 페르소나 및 정밀한 채점 구조를 완벽하게 유지합니다.

solar-embedding-1-large: 코드 도메인 및 이력서 문맥의 미세한 뉘앙스를 정교한 벡터 공간으로 매핑합니다.

ChromaDB & Commit-Hash 캐싱: 매 요청마다 무겁게 깃허브 코드를 재임베딩하지 않도록, 최신 커밋 해시 기반의 Collection Caching 전략을 취해 중복 임베딩 비용과 Latency를 획기적으로 감축했습니다.

🔒 5. 프로덕션 하드닝 및 보안 (Production Security)

실제 프로덕션 배포 및 대기업 규격을 만족하기 위해 설계된 보안 계층입니다.

컨테이너 보안 (Non-Root User & Multi-Stage):
실행 컨테이너 내에서 불필요한 uv 도구와 root 권한을 영구 박탈하고, 최소 권한의 시스템 유저인 appuser 계정으로 서비스를 가동하여 컨테이너 탈취가 호스트 전체의 권한 상승(Escaping) 취약점으로 번지는 것을 차단했습니다.

이중 망 분리 격리 (Network Segmentation):
docker-compose 아키텍처 상에서 외부와 소통하는 frontend-network와 내부 DB 전용망인 backend-network로 분할하여 프론트엔드 노드가 탈취되더라도 핵심 벡터 DB와 LLM 인프라까지 2차 침투하는 것을 기술적으로 원천 격리했습니다.

멀티 유저 세션 격리 (UUID Thread Isolation):
Streamlit의 무한 Rerun 루프에 대응해 브라우저 탭마다 고유한 uuid4 기반의 세션 식별자를 생성하고 이를 백엔드 LangGraph의 thread_id와 다이렉트 매핑하여, 동시 접속 환경에서도 사용자 간의 대화가 서로 꼬이거나 누수되는 사고를 원천 방어했습니다.

🏃 6. 실행 가이드 (Getting Started)

📂 1) 환경 변수 설정 (.env)

프로젝트 루트 폴더에 .env 파일을 생성하고 아래 인증 정보를 입력해 주세요.

UPSTAGE_API_KEY=your_upstage_api_key_here
GITHUB_TOKEN=your_github_personal_token_here


📦 2) 가상환경 구축 및 패키지 설치 (uv 활용 권장)

# 가상환경 생성
python -m venv .venv
.\.venv\Scripts\activate

# 의존성 패키지 설치
pip install -r pyproject.toml


🚀 3) 서비스 구동

Terminal 1 (백엔드 uvicorn 가동):

.\.venv\Scripts\python.exe -m uvicorn app.main:app --reload --port 8000


Terminal 2 (프론트엔드 streamlit 가동):

.\.venv\Scripts\python.exe -m streamlit run frontend/ui.py


👥 7. 멤버 정보 (Team Members)
팀원: [이장혁,서용수,조채환,박태경]

Repository: https://github.com/tttae210-sys/gitinsight_agent
