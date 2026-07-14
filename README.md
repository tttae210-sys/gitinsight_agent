# 🤖 GitInsight Agent

GitHub 소스코드 정적 분석 및 이력서·기업 인재상(JD) 다중 교차 검증 기반 AI 모의 기술면접 에이전트

**KNU-Upstage AI Service Design - 2조 (이게뭐조)**  
*최종 발표일: 2026. 07. 14*

---

# 📌 1. 프로젝트 개요 (Introduction)

**GitInsight Agent**는 지원자의 이력서(주장, Claim)와 실제 GitHub 저장소의 소스코드(증거, Proof), 그리고 목표로 하는 기업 인재상(Job Description)을 실시간으로 다중 교차 분석하여, 단순 암기 위주의 기술 면접을 탈피하고 실무 역량을 팩트 기반으로 정밀 검증하는 AI 모의면접 플랫폼입니다.

기존의 획일적인 모의면접 서비스와 달리, **LangGraph 멀티 에이전트 아키텍처**를 기반으로 지원자의 대답 품질에 맞추어 실시간 적응형 난이도 제어(Easy ➡️ Medium ➡️ Hard) 및 3-Strike 소크라테스식 코드 하이라이팅 힌트 시스템을 제공하여 수준 높은 맞춤형 기술 면접 경험을 선사합니다.

---

# 🏛️ 2. 서비스 아키텍처 (System Architecture)

GitInsight는 컴포넌트 간 단일 책임 원칙(SRP)과 인프라 격리성을 확보한 비동기 컨테이너식 마이크로서비스 아키텍처를 지향합니다.

```text
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
         ┌────────────────────────┼────────────────────────┐
         ▼                        ▼                        ▼
┌─────────────────┐      ┌──────────────────┐      ┌───────────────────────────────────┐
│    Vector DB    │      │ Company Profiles │      │ LangGraph Stateful Agent Workflow │
│   (ChromaDB)    │      │(Kakao/Naver/Toss)│      │                                   │
│                 │      │  (Line/Coupang)  │      │                ┌─ [START] ─> builder
│ - Commit-Hash   │      │                  │      │                │                 │  
│   Caching       │      │ - JD/Core Value  │      │                │                 ▼  
│ - Upstage Solar │      │   동적 컨텍스트    │      │  classifier ──┼─ [ANSWER] ─> evaluator
│   Embedding     │      │   주입 매커니즘  │      │                │                 │  
│                 │      │                  │      │                │     ├─ [PASS] -> next_q
│ - Persistent    │      │                  │      │                │     ├─ [HINT] -> hint  
│   Disk Storage  │      │                  │      │                │     └─ [FAIL] -> report
└─────────────────┘      └──────────────────┘      └───────────────────────────────────┘
