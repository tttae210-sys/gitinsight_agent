🤖 GitInsight Agent
GitHub 소스코드 정적 분석 및 이력서·기업 인재상(JD) 다중 교차 검증 기반 AI 모의 기술면접 에이전트

KNU-Upstage AI Service Design - 2조 (이게뭐조)

최종 발표일: 2026. 07. 14

📌 1. 프로젝트 개요 (Introduction)
GitInsight Agent는 지원자의 이력서(주장, Claim)와 실제 GitHub 저장소의 소스코드(증거, Proof), 그리고 목표로 하는 기업 인재상(Job Description)을 실시간으로 다중 교차 분석하여, 단순 암기 위주의 기술 면접을 탈피하고 실무 역량을 팩트 기반으로 정밀 검증하는 AI 모의면접 플랫폼입니다.

기존의 획일적인 모의면접 서비스와 달리, LangGraph 멀티 에이전트 아키텍처를 기반으로 지원자의 대답 품질에 맞추어 실시간 적응형 난이도 제어(Easy ➡️ Medium ➡️ Hard) 및 3-Strike 소크라테스식 코드 하이라이팅 힌트 시스템을 제공하여 수준 높은 맞춤형 기술 면접 경험을 선사합니다.

🏛️ 2. 서비스 아키텍처 (System Architecture)
GitInsight는 컴포넌트 간 단일 책임 원칙(SRP)과 인프라 격리성을 확보한 비동기 컨테이너식 마이크로서비스 아키텍처를 지향합니다.

Plaintext
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
         ┌────────────────────┼────────────────────┐
         ▼                    ▼                    ▼
┌─────────────────┐ ┌──────────────────┐ ┌───────────────────────────────────┐
│  Vector DB      │ │  Company Profiles│ │ LangGraph Stateful Agent Workflow │
│  (ChromaDB)     │ │ (Kakao/Naver/Toss│ │                                   │
│                 │ │  Line/Coupang)   │ │                ┌─ [START] ─> builder
│ - Commit-Hash   │ │                  │ │                │                 │  
│   Caching       │ │ - JD / Core Value│ │                │                 ▼  
│ - Upstage Solar │ │   동적 컨텍스트    │ │  classifier ──┼─ [ANSWER] ─> evaluator
│   Embedding     │ │   주입 매커니즘  │ │                │                 │  
│                 │ │                  │ │                │     ├─ [PASS] -> next_q
│ - Persistent    │ │                  │ │                │     ├─ [HINT] -> hint  
│   Disk Storage  │ │                  │ │                │     └─ [FAIL] -> report
└─────────────────┘ └──────────────────┘ └───────────────────────────────────┘
🔁 LangGraph 에이전트 상태 전이 제어 흐름
[전처리 파이프라인 — 최초 빌드 시 1회]

classifier ──> builder ──> question_extractor (질문 풀 5~7개 사전 구축) ──> END

[실시간 면접 문답 트랙 — 매 턴 반복]

classifier (유저 자연어 입력 분석 및 인텐트 파이프라인 분기)

├─ ANSWER ──> evaluator (정밀 채점)

│   ├─ PASS ──> next_question (풀에서 질문 디스패치) ──> END

│   ├─ HINT ──> hint_agent (노란 형광펜 힌트 제공) ──> END

│   ├─ ANSWER_REQUEST ──> answer_provider (모범답안 공개) ──> END

│   └─ FAIL ──> reporter (3-Strike 아웃 리포트) ──> END

├─ ANSWER_REQUEST ──> answer_provider (포기성 정답 및 해설 요청 즉시 처리) ──> END

├─ SKIP ──> next_question (답변 건너뛰기 및 다음 질문 로드) ──> END

└─ CHAT ──> chat_node (일상 대화 및 시스템 안내) ──> END

🚀 3. 핵심 킬러 기능 (Killer Features)
🎯 ① 3차원 다중 교차 검증 (Resume × GitHub × Company Profile)
지원자의 이력서(Claim)와 실제 깃허브 소스코드(Proof)를 대조하는 것을 넘어, company_profiles.py에 정의된 목표 기업(네이버, 카카오, 토스 등)의 실제 기술 스택 및 인재상(JD)을 분석 루프에 결합했습니다. 목표 기업이 요구하는 핵심 아키텍처 역량에 맞추어 질문 생성기(question_extractor)가 동적으로 타겟팅된 면접 문항을 출제합니다.

⚡ ② 듀얼 LLM 기반 동적 라우팅 및 적응형 난이도 제어
의도 판별 동적 라우팅 (classifier): 유저의 입력을 단순히 if-else 키워드로 매칭하는 한계를 넘어서, LLM이 문맥의 성격을 파악하여 기술 답변(ANSWER)과 일상 대화(CHAT)를 스스로 분별해 경로를 결정합니다.

실시간 난이도 조절 (evaluator): 답변의 정합성과 깊이를 점수화하여 다음 질문의 수준을 EASY(CS 원리 재점검), MEDIUM(실무 기술 점검), HARD(컴파일러/메모/동시성 아키텍처 압박) 트랙으로 실시간 조율합니다.

⚾ ③ 3-Strike 힌트 루프 & Yellow Marker 코드 하이라이팅
답변이 부실할 경우 정답을 즉시 노출하지 않고, 관련 소스코드의 실제 라인 번호 범위를 노란색 형광펜으로 지목(HighlightMetadata)해 주며 지원자 스스로 답을 복기할 수 있도록 소크라테스식 힌트를 유도합니다.

🛠️ 5. 기술 스택 및 아키텍처 결정 이유 (Tech Stack)
uv (Rust-based Fast Package Manager): 기존 pip나 poetry 대비 최대 10~100배 빠른 패키지 설치 속도를 자랑하는 최신 빌드 도구 uv를 도입하여 가상환경 빌드 속도를 극대화하고 uv.lock을 통해 일관된 패키지 디펜던시를 고정했습니다.

FastAPI (ASGI, Async): 무거운 LLM API 연산 및 ChromaDB RAG 연산 대기 시간(I/O Bound)의 병목을 비동기 루틴으로 완벽하게 해결합니다.  
ZIP

ChromaDB & Commit-Hash Caching: 매번 무겁게 깃허브 코드를 재임베딩하지 않도록, 최신 커밋 해시 기반의 Collection Caching 전략을 취해 중복 임베딩 비용과 지연 시간을 획기적으로 감축했습니다.

🔒 6. 프로덕션 하드닝 및 보안 (Production Security)
컨테이너 보안 (Multi-Stage & Non-Root): Dockerfile.api 및 Dockerfile.frontend 설계 시 멀티 스테이지 빌드를 사용하여 경량화를 달성하였고, 컨테이너 내부에서 root가 아닌 최소 권한의 appuser 계정으로 가동하여 호스트 탈취 취약점을 차단했습니다.

이중 망 분리 격리 (Network Segmentation): docker-compose 아키텍처 상에서 외부 브라우저 세션과 직접 만나는 frontend-network와, 내부 백엔드-DB 전용망인 backend-network로 분할하여 프론트엔드가 해킹당하더라도 내부 소스코드 DB와 아키텍처가 2차 침투당하는 것을 물리적으로 격리했습니다.

🏃 7. 실행 가이드 (Getting Started)
🐳 Docker Compose를 사용한 원클릭 가동 (권장)
설치 및 로컬 환경 세팅의 번거로움 없이 Docker를 통해 백엔드와 프론트엔드를 한 번에 빌드하고 통합 실행할 수 있습니다.

1. 환경 변수 설정

Bash
cp .env.example .env
.env 파일을 열고 UPSTAGE_API_KEY 및 GITHUB_TOKEN을 기입해 주세요.  
ZIP

2. 컨테이너 일괄 빌드 및 백그라운드 가동

Bash
docker-compose up --build -d
3. 브라우저로 서비스 접속

Frontend (Streamlit) : http://localhost:8501

Backend (FastAPI API) : http://localhost:8000/docs

👥 8. 이게뭐조 (2조) 멤버 정보
팀원: 이장혁, 서용수, 조채환, 박태경
