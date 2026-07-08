import streamlit as st
import time
import requests
import json
import os

# 1. 페이지 레이아웃 및 디자인 설정
st.set_page_config(
    page_title="GitInsight Interview Tutor",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

# 2. 세션 상태(Session State) 초기화 (대화 기록 및 대시보드 데이터 보존)
if "messages" not in st.session_state:
    st.session_state.messages = [
        {
            "role": "assistant", 
            "content": "안녕하세요, 민우 님! GitInsight 모의 면접 튜터입니다. 분석을 원하시는 GitHub Repository URL을 왼쪽에 입력하고 질문을 시작해 보세요!"
        }
    ]
if "tech_stack" not in st.session_state:
    st.session_state.tech_stack = []
if "extracted_chunks" not in st.session_state:
    st.session_state.extracted_chunks = []
if "evaluation" not in st.session_state:
    st.session_state.evaluation = {}
if "final_report" not in st.session_state:
    st.session_state.final_report = ""
if "current_question" not in st.session_state:
    st.session_state.current_question = ""
if "retry_count" not in st.session_state:
    st.session_state.retry_count = 0
if "answer_history" not in st.session_state:
    st.session_state.answer_history = []

# 3. 사이드바 UI 구성
with st.sidebar:
    st.header("⚙️ 프로젝트 설정")
    st.markdown("분석할 GitHub 레포지토리 정보를 기입해 주세요.")
    
    # 깃허브 URL 입력창 (반응형 상태 관리)
    repo_url = st.text_input(
        "GitHub Repository URL", 
        placeholder="https://github.com/username/repository",
        help="에이전트가 코드를 파싱하고 모의 면접 족보를 추출할 대상 주소입니다."
    )
    
    if repo_url:
        st.success(f"🔗 연결 성공: {repo_url.split('/')[-1]}")
    else:
        st.warning("⚠️ 레포지토리 주소를 먼저 입력해 주세요.")
        
    st.write("---")
    st.header("🛠️ 대화 컨트롤러")
    
    # 대화 및 대시보드 리셋 기능
    if st.button("🗑️ 면접 기록 초기화", use_container_width=True):
        st.session_state.messages = [
            {"role": "assistant", "content": "대화 기록이 초기화되었습니다. 새로운 면접을 시작하세요!"}
        ]
        st.session_state.tech_stack = []
        st.session_state.extracted_chunks = []
        st.session_state.evaluation = {}
        st.session_state.final_report = ""
        st.session_state.current_question = ""
        st.session_state.retry_count = 0
        st.session_state.answer_history = []
        st.rerun()

# 4. 메인 화면 레이아웃 분할 (2-Column 대시보드 구성)
col_chat, col_dashboard = st.columns([1.1, 0.9], gap="large")

# ==========================================
# [좌측 영역] 💬 실시간 모의 면접 대화창
# ==========================================
with col_chat:
    st.subheader("💬 모의 면접 및 질문 답변")
    st.caption("AI 면접관의 압박 질문을 받고 답변을 입력해 보세요.")
    
    # 기존 대화 흐름 출력
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

# ==========================================
# [우측 영역] 📊 실시간 깃인사이트 분석 대시보드
# ==========================================
with col_dashboard:
    st.subheader("📊 GitInsight 실시간 분석")
    st.caption("LangGraph 에이전트가 코드를 분석하고 채점하는 실시간 현황판입니다.")
    
    # 탭 메뉴 구성
    tab_code, tab_report = st.tabs(["📂 검출된 기술 및 코드", "📝 평가 및 리포트"])
    
    with tab_code:
        # 1. 기술 스택 시각화
        st.write("### 🛠️ 검출된 프로젝트 기술 스택")
        if st.session_state.tech_stack:
            cols = st.columns(max(len(st.session_state.tech_stack), 1))
            for i, tech in enumerate(st.session_state.tech_stack):
                cols[i].info(f"**{tech}**")
        else:
            st.info("코드를 파싱하기 전입니다. 첫 대화가 시작되면 자동으로 채워집니다.")
            
        st.write("---")
        
        # 2. 파싱된 핵심 코드 조각 출력
        st.write("### 📂 RAG 기반 핵심 소스코드")
        if st.session_state.extracted_chunks:
            for idx, chunk in enumerate(st.session_state.extracted_chunks):
                file_path = chunk.get("file_path", "unknown_file")
                with st.expander(f"📄 [{idx+1}] {file_path}", expanded=True):
                    st.code(chunk.get("content") or chunk.get("code", ""), language=chunk.get("language", "python"))
        else:
            st.info("질문과 밀접한 연관이 있는 핵심 파일이 검색되면 여기에 코드가 렌더링됩니다.")
            
    with tab_report:
        # 3. 답변 정밀 채점 결과
        st.write("### 📋 현재 답변 평가")
        if st.session_state.evaluation:
            score = st.session_state.evaluation.get("score", "N/A")
            is_passed = st.session_state.evaluation.get("passed", False)
            
            metric_col1, metric_col2 = st.columns(2)
            metric_col1.metric("종합 점수", f"{score}점")
            metric_col2.metric("패스 여부", "PASS" if is_passed else "RE-TRY")
            
            st.markdown(f"**상세 채점 기준:**\n{st.session_state.evaluation.get('reason', '')}")
        else:
            st.info("유저가 면접 질문에 답변을 완료하면 AI의 정밀 평가 결과가 실시간 기록됩니다.")
            
        st.write("---")
        
        # 4. 최종 리팩토링 리포트
        st.write("### 📝 최종 리팩토링 가이드")
        if st.session_state.final_report:
            st.markdown(st.session_state.final_report)
        else:
            st.info("면접의 전 과정이 완료되면 개선 가이드라인 리포트가 생성됩니다.")

# ==========================================
# 5. 사용자 채팅 및 실시간 스트리밍 처리
# ==========================================
if prompt := st.chat_input("질문을 입력하세요. (예: 내 코드에서 발생 가능한 에러 분석해줘)"):
    
    # 1) 유저 입력 화면 표시 및 세션 저장 (왼쪽 채팅창 전용)
    st.session_state.messages.append({"role": "user", "content": prompt})
    with col_chat:
        with st.chat_message("user"):
            st.markdown(prompt)
            
        # 2) AI 답변 처리 영역
        with st.chat_message("assistant"):
            status_placeholder = st.empty()
            response_placeholder = st.empty()
            
            api_base_url = os.getenv("API_BASE_URL", "http://localhost:8000/api/v1")
            backend_url = f"{api_base_url}/chat"
            
            # 조원분의 api.py 호환성을 위해 query와 message를 모두 탑재하여 전송합니다.
            payload = {
                "query": prompt,
                "message": prompt, 
                "repo_url": repo_url if repo_url else None,
                "user_id": "jang_hyuk",
                "current_question": st.session_state.current_question,
                "current_retry_count": st.session_state.retry_count,
                "answer_history": st.session_state.answer_history,
            }
            
            full_response = ""
            status_placeholder.info("⚡ GitInsight 에이전트 분석 중...")
            
            try:
                # 8000번 백엔드 서버에 SSE 스트리밍 요청 전송 (stream=True)
                with requests.post(backend_url, json=payload, stream=True, timeout=15) as response:
                    if response.status_code == 200:
                        for line in response.iter_lines():
                            if line:
                                decoded_line = line.decode('utf-8').strip()
                                if decoded_line.startswith("data: "):
                                    data_json_str = decoded_line[6:]
                                    event_data = json.loads(data_json_str)
                                    
                                    event_type = event_data.get("event")
                                    inner_data = event_data.get("data", {})
                                    
                                    # 백엔드에서 data 필드를 문자열(String)로 보낸 경우에 대비한 자동 안전 파싱
                                    if isinstance(inner_data, str):
                                        try:
                                            inner_data = json.loads(inner_data)
                                        except Exception:
                                            pass
                                    
                                    # Case A: 에이전트 내부 노드 변경 이벤트 처리 (시각화 연동)
                                    if event_type == "node":
                                        node_name = event_data.get("node") or "Processing"
                                        
                                        if node_name == "intent_classifier":
                                            status_placeholder.info("🔍 [1단계] 사용자의 질문 의도를 정밀하게 분석하는 중...")
                                        elif node_name == "code_build":
                                            status_placeholder.warning("📚 [2단계] 소스코드 저장소에서 관련 지식을 임베딩 검색 중...")
                                        elif node_name == "interview_extract":
                                            status_placeholder.success("✍️ [3단계] 검색된 코드 맥락을 분석하여 면접 질문을 구성 중...")
                                        elif node_name == "evaluation":
                                            status_placeholder.info("🧪 [4단계] 답변을 루브릭으로 평가하는 중...")
                                        elif node_name == "feedback_gen":
                                            status_placeholder.success("📝 [5단계] 최종 리포트를 생성하는 중...")
                                            
                                        # 실시간 상태 세션 메모리 주입
                                        if isinstance(inner_data, dict):
                                            output_state = inner_data.get("output", {}) if "output" in inner_data else inner_data
                                            if "tech_stack" in output_state and output_state["tech_stack"]:
                                                st.session_state.tech_stack = output_state["tech_stack"]
                                            if "extracted_chunks" in output_state and output_state["extracted_chunks"]:
                                                st.session_state.extracted_chunks = output_state["extracted_chunks"]
                                            if "evaluation" in output_state and output_state["evaluation"]:
                                                st.session_state.evaluation = output_state["evaluation"]
                                            if "final_report" in output_state and output_state["final_report"]:
                                                st.session_state.final_report = output_state["final_report"]
                                    
                                    # Case B: 최종 완료 이벤트 처리 (답변 스트리밍 효과 적용)
                                    elif event_type == "done":
                                        status_placeholder.empty()
                                        answer = inner_data.get("answer", "") if isinstance(inner_data, dict) else ""
                                        if not answer and isinstance(inner_data, str):
                                            answer = inner_data

                                        if isinstance(inner_data, dict):
                                            st.session_state.current_question = inner_data.get("next_question", "")
                                            st.session_state.retry_count = inner_data.get("new_retry_count", 0)
                                            if inner_data.get("tech_stack"):
                                                st.session_state.tech_stack = inner_data["tech_stack"]
                                            if inner_data.get("extracted_chunks"):
                                                st.session_state.extracted_chunks = inner_data["extracted_chunks"]
                                            if inner_data.get("feedback"):
                                                st.session_state.evaluation = {
                                                    "score": inner_data.get("evaluation_score", 0),
                                                    "reason": inner_data.get("feedback", ""),
                                                    "passed": inner_data.get("status") in ("PASS", "REPORT"),
                                                }
                                            if inner_data.get("final_report"):
                                                st.session_state.final_report = inner_data["final_report"]
                                            if inner_data.get("status") == "REPORT":
                                                st.session_state.current_question = ""
                                                st.session_state.retry_count = 0
                                        
                                        for word in answer.split(" "):
                                            full_response += word + " "
                                            response_placeholder.markdown(full_response + "▌")
                                            time.sleep(0.02)
                                        response_placeholder.markdown(full_response)
                                        
                    else:
                        status_placeholder.empty()
                        error_msg = f"⚠️ 서버 비정상 응답 (코드: {response.status_code})"
                        response_placeholder.error(error_msg)
                        full_response = error_msg
                        
            except requests.exceptions.ConnectionError:
                status_placeholder.empty()
                error_msg = "⚠️ **백엔드 서버(포트 8000) 연결 거부**\n\n현재 로컬 백엔드 서버가 켜져 있지 않습니다. 터미널에서 `uv run uvicorn app.main:app --reload --port 8000` 명령어로 백엔드를 가동해 주세요!"
                response_placeholder.error(error_msg)
                full_response = error_msg
                
            except Exception as e:
                status_placeholder.empty()
                error_msg = f"⚠️ **요청 처리 중 예기치 못한 에러 발생**\n\n에러 내용: `{str(e)}`"
                response_placeholder.error(error_msg)
                full_response = error_msg
                
        st.session_state.messages.append({"role": "assistant", "content": full_response})
        st.session_state.answer_history.append(prompt)
        st.rerun()
