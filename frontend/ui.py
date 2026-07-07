import streamlit as st
import time

# 1. 페이지 기본 설정
st.set_page_config(
    page_title="GitInsight Agent Test",
    page_icon="💻",
    layout="wide"
)

# 2. 세션 스테이트(대화 기록 저장소) 초기화
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "안녕하세요! GitInsight 테스트 챗봇입니다. 하단의 입력창에 질문을 입력하거나, 왼쪽 사이드바의 버튼을 눌러 테스트해 보세요!"}
    ]

# 3. 사이드바 구성
with st.sidebar:
    st.header("⚙️ 테스트 컨트롤러")
    st.markdown("조원분이 백엔드를 완성하기 전, 프론트엔드 기능과 UI를 검증하는 도구입니다.")
    
    # [테스트 버튼 1] 코드 템플릿 불러오기
    if st.button("📝 샘플 코드 불러오기", use_container_width=True):
        sample_code = """```python
# [테스트용 샘플 파이썬 코드]
def analyze_repository(repo_url):
    print(f"Analyzing repository: {repo_url}")
    return {
        "status": "success",
        "agent_insight": "이 리포지토리는 깔끔하게 관리되고 있습니다."
    }
```"""
        st.session_state.messages.append({"role": "assistant", "content": f"요청하신 샘플 코드를 불러왔습니다:\n{sample_code}"})
        st.rerun()

    # [테스트 버튼 2] 대화 리셋
    if st.button("🗑️ 대화 기록 초기화", use_container_width=True):
        st.session_state.messages = [
            {"role": "assistant", "content": "대화 기록이 초기화되었습니다. 다시 테스트를 진행해 보세요!"}
        ]
        st.rerun()

# 4. 메인 화면 타이틀
st.title("🤖 GitInsight 에이전트 인터페이스")
st.caption("현재 상태: 로컬 프론트엔드 독립 테스트 모드 (백엔드 미연결)")

# 5. 기존 대화 기록 출력
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 6. 사용자 채팅 입력 처리
if prompt := st.chat_input("테스트 질문을 입력해 보세요. (예: 코드 리뷰해줘)"):
    
    # 사용자가 입력한 말 화면에 표시 및 저장
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
        
    # AI 답변 시뮬레이션 영역
    with st.chat_message("assistant"):
        response_placeholder = st.empty()
        
        # 입력한 단어에 따라 조건문으로 다른 가짜 답변 주기 (테스트용)
        if "코드" in prompt or "code" in prompt:
            answer = "임시 백엔드 에이전트 응답입니다: 입력하신 내용에 '코드'가 포함되어 있어, 파이썬 분석 결과를 시뮬레이션합니다.\n\n```python\nprint('Hello GitInsight!')\n```"
        elif "안녕" in prompt:
            answer = "반갑습니다! 팀원분이 백엔드 API를 완성해서 연결하면 제 실제 인공지능 답변이 여기에 출력될 예정입니다. 지금은 화면 테스트 중입니다! 😎"
        else:
            answer = f"**'{prompt}'**에 대한 백엔드 에이전트의 임시 답변입니다. 프론트엔드 UI가 끊김 없이 실시간으로 작동하는지 확인하기 위해 텍스트 스트리밍을 흉내 냅니다."
        
        # 글자가 타자 치듯 나오는 효과 (스트리밍 시뮬레이션)
        full_response = ""
        for chunk in answer.split(" "):
            full_response += chunk + " "
            time.sleep(0.08)
            response_placeholder.markdown(full_response + "▌")
        response_placeholder.markdown(full_response)
        
    # AI 답변도 대화 기록에 저장
    st.session_state.messages.append({"role": "assistant", "content": full_response})