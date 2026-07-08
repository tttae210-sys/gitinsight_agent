import streamlit as st
import requests
import time

# 페이지 기본 설정 (가장 위에 위치해야 합니다)
st.set_page_config(
    page_title="GitInsight - AI 면접 튜터",
    page_icon="🤖",
    layout="centered"
)

# ==========================================
# 1단계: 면접 상태를 저장할 금고(Session State) 초기화
# ==========================================
if 'user_id' not in st.session_state:
    st.session_state.user_id = "min_woo"

if 'retry_count' not in st.session_state:
    st.session_state.retry_count = 0

if 'repo_url' not in st.session_state:
    st.session_state.repo_url = ""

if 'chat_history' not in st.session_state:
    st.session_state.chat_history = [
        {
            "role": "assistant",
            "content": "안녕하세요! GitInsight AI 면접관입니다. 제출하신 GitHub 레포지토리를 분석했습니다.\n\n**첫 번째 질문:**\n프로젝트에서 다중 서버 환경을 고려해 Redis 캐시를 도입하셨는데, 로컬 인메모리 캐시 대신 굳이 Redis를 선택해 구축하신 구체적인 이유가 무엇인가요?"
        }
    ]

# ==========================================
# 헤더 영역
# ==========================================
st.title("🤖 GitInsight")
st.subheader("내 프로젝트 기반 맞춤형 면접 튜터")
st.write("작성하신 실제 코드를 바탕으로 날카로운 꼬리 질문과 맞춤형 힌트를 제공합니다.")

# ==========================================
# 사이드바 영역
# ==========================================
with st.sidebar:
    st.header("⚙️ 프로젝트 설정")
    st.markdown("분석할 GitHub 레포지토리 정보를 기입해 주세요.")

    repo_url = st.text_input(
        "GitHub Repository URL", 
        value=st.session_state.repo_url,
        placeholder="https://github.com/username/repository",
        help="에이전트가 코드를 파싱하고 모의 면접 질문을 구성할 대상 주소입니다."
    )
    st.session_state.repo_url = repo_url

    if repo_url:
        st.success(f"🔗 연결 성공: {repo_url.split('/')[-1]}")
    else:
        st.warning("⚠️ 레포지토리 주소를 먼저 입력해 주세요.")

    st.markdown("---")
    st.header("📋 면접 정보")
    st.info(f"👤 사용자 ID: {st.session_state.user_id}")

    st.markdown("---")
    st.subheader("⚾ 힌트 기회 (Strike Count)")

    strikes = st.session_state.retry_count
    if strikes == 0:
        st.markdown("### ⚪ ⚪ ⚪ (안전)")
    elif strikes == 1:
        st.markdown("### 🔴 ⚪ ⚪ (1차 힌트 소모)")
    elif strikes == 2:
        st.markdown("### 🔴 🔴 ⚪ (경고! 마지막 힌트)")
    else:
        st.markdown("### 🔴 🔴 🔴 (기회 모두 소모 - 오답 처리)")
        
    st.caption("답변이 부족할 때마다 빨간 불이 켜지며 더 구체적인 힌트가 제공됩니다. 3회 실패 시 강사 모드로 정답 해설이 제공됩니다.")

    if st.button("면접 다시 시작하기", use_container_width=True):
        st.session_state.retry_count = 0
        st.session_state.repo_url = ""
        st.session_state.chat_history = [
            {
                "role": "assistant", 
                "content": "면접이 초기화되었습니다!\n\n**첫 번째 질문:**\n프로젝트에서 다중 서버 환경을 고려해 Redis 캐시를 도입하셨는데, 로컬 인메모리 캐시 대신 굳이 Redis를 선택해 구축하신 구체적인 이유가 무엇인가요?"
            }
        ]
        st.rerun()

# ==========================================
# 대화 기록 렌더링
# ==========================================
for message in st.session_state.chat_history:
    with st.chat_message(message["role"]):
        st.write(message["content"])

# ==========================================
# 사용자 답변 처리
# ==========================================
if prompt := st.chat_input("면접관의 질문에 답변해 보세요!"):
    with st.chat_message("user"):
        st.write(prompt)
    st.session_state.chat_history.append({"role": "user", "content": prompt})

    with st.status("AI 면접관이 답변을 심사하는 중입니다...", expanded=True) as status:
        st.write("🔍 GitHub 저장소의 원본 코드 구조 탐색 중...")
        time.sleep(0.8)
        
        st.write("📚 백엔드 아키텍처 및 면접 족보 DB 매칭 중...")
        time.sleep(1.0)
        
        st.write("🧠 답변 내용 채점 및 튜터링 피드백 구성 중...")
        
        payload = {
            "user_id": st.session_state.user_id,
            "user_answer": prompt,
            "current_retry_count": st.session_state.retry_count,
            "repo_url": st.session_state.repo_url if st.session_state.repo_url else None
        }
        
        try:
            API_URL = "http://localhost:8000/api/v1/chat/sync"
            response = requests.post(API_URL, json=payload, timeout=10)
            
            if response.status_code == 200:
                response_data = response.json()
                result_data = response_data.get("data", {})
                
                feedback = result_data.get("feedback", "")
                next_q = result_data.get("next_question", "")
                ai_message = f"{feedback}\n\n---\n\n**다음 질문:**\n{next_q}"
                
                new_retry_count = result_data.get("new_retry_count", 0)
                status_code = result_data.get("status", "HINT")
                
                st.session_state.retry_count = new_retry_count
                
                status.update(label="분석 완료! 다음 단계로 넘어갑니다.", state="complete", expanded=False)
                
                with st.chat_message("assistant"):
                    st.write(ai_message)
                    st.caption(f"판정 결과: {status_code} | 누적 힌트: {new_retry_count}/3")
                st.session_state.chat_history.append({"role": "assistant", "content": ai_message})
                
                st.rerun()
                
            else:
                status.update(label="분석 실패 (오류 발생)", state="error", expanded=True)
                st.error(f"서버 에러가 발생했습니다. 상태 코드: {response.status_code}")
                
        except requests.exceptions.RequestException as e:
            status.update(label="네트워크 연결 실패", state="error", expanded=True)
            st.error("FastAPI 서버가 켜져 있는지 확인해 주세요! (python -m uvicorn main:app --reload)")