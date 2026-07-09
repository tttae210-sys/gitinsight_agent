import streamlit as st
import time
import requests
import json
import os

# ==========================================
# 0. 커스텀 형광펜 렌더링 함수
# ==========================================
def render_highlighted_code(code_text: str, start_line: int = None, end_line: int = None):
    """
    Streamlit 화면에 소스코드를 렌더링하되, 지정된 라인 범위(start_line ~ end_line)에
    형광펜 효과(하이라이팅)를 주어 HTML로 출력합니다.
    """
    lines = code_text.split("\n")
    html_lines = []
    
    style = """
    <style>
        .code-container {
            background-color: #0e1117;
            color: #c9d1d9;
            font-family: 'Courier New', Courier, monospace;
            font-size: 14px;
            line-height: 1.5;
            padding: 15px;
            border-radius: 8px;
            overflow-x: auto;
            border: 1px solid #30363d;
        }
        .code-line {
            display: flex;
            width: 100%;
        }
        .line-number {
            color: #8b949e;
            text-align: right;
            width: 40px;
            padding-right: 15px;
            user-select: none;
            border-right: 1px solid #30363d;
        }
        .line-content {
            padding-left: 15px;
            white-space: pre;
        }
        .highlighted {
            background-color: rgba(218, 165, 32, 0.25);
            border-left: 3px solid #ffca28;
        }
    </style>
    """
    
    html_lines.append('<div class="code-container">')
    for idx, line in enumerate(lines, 1):
        safe_line = line.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        
        is_highlighted = False
        if start_line is not None and end_line is not None:
            if start_line <= idx <= end_line:
                is_highlighted = True
                
        line_class = "code-line highlighted" if is_highlighted else "code-line"
        
        html_lines.append(f"""
        <div class="{line_class}">
            <div class="line-number">{idx}</div>
            <div class="line-content">{safe_line if safe_line.strip() != "" else " "}</div>
        </div>
        """)
    html_lines.append('</div>')
    st.markdown(style + "".join(html_lines), unsafe_allow_html=True)


# ==========================================
# 1. 페이지 레이아웃 및 세션 초기화
# ==========================================
st.set_page_config(
    page_title="GitInsight Interview Tutor",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded"
)

if "user_id" not in st.session_state:
    st.session_state.user_id = "장혁"
if "retry_count" not in st.session_state:
    st.session_state.retry_count = 0  # 🔴 3-Strike 카운터
if "current_highlight" not in st.session_state:
    st.session_state.current_highlight = None  # 🔴 형광펜 메타데이터
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": f"안녕하세요, {st.session_state.user_id} 님! GitInsight 모의 면접 튜터입니다. 분석을 원하시는 GitHub Repository URL을 왼쪽에 입력하고 질문을 시작해 보세요!"}
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
if "answer_history" not in st.session_state:
    st.session_state.answer_history = []
if "repo_url" not in st.session_state:
    st.session_state.repo_url = ""  # 세션 상태로 영구 보존


# ==========================================
# 2. 사이드바 UI (3-Strike 시각화)
# ==========================================
with st.sidebar:
    st.header("⚙️ 프로젝트 설정")
    st.markdown("분석할 GitHub 레포지토리 정보를 기입해 주세요.")

    # 깃허브 URL 입력창 (세션 상태로 값을 영구 보존 — 채팅 submit 시 값 유지)
    repo_url_input = st.text_input(
        "GitHub Repository URL",
        value=st.session_state.repo_url,
        placeholder="https://github.com/username/repository",
        help="에이전트가 코드를 파싱하고 모의 면접 족보를 추출할 대상 주소입니다."
    )
    if repo_url_input != st.session_state.repo_url:
        st.session_state.repo_url = repo_url_input
        st.rerun()

    repo_url = st.session_state.repo_url

    if repo_url:
        st.success(f"🔗 연결 성공: {repo_url.split('/')[-1]}")
    else:
        st.warning("⚠️ 레포지토리 주소를 먼저 입력해 주세요.")

    st.write("---")

    # 🔴 [3-Strike 적용] 스트라이크 아웃 형태로 힌트 현황 시각화
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
    st.write("---")

    st.header("🛠️ 대화 컨트롤러")
    if st.button("🗑️ 면접 기록 초기화", use_container_width=True):
        st.session_state.messages = [
            {"role": "assistant", "content": f"대화 기록이 초기화되었습니다. 새로운 면접을 시작하세요, {st.session_state.user_id} 님!"}
        ]
        st.session_state.tech_stack = []
        st.session_state.extracted_chunks = []
        st.session_state.evaluation = {}
        st.session_state.final_report = ""
        st.session_state.retry_count = 0
        st.session_state.current_highlight = None
        st.session_state.answer_history = []
        # repo_url은 초기화하지 않음 (다시 입력하는 불편함 방지)
        st.rerun()


# ==========================================
# 3. 메인 화면 레이아웃 (채팅 및 대시보드)
# ==========================================
col_chat, col_dashboard = st.columns([1.1, 0.9], gap="large")

with col_chat:
    st.subheader("💬 모의 면접 및 질문 답변")
    st.caption("AI 면접관의 압박 질문을 받고 답변을 입력해 보세요.")
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

with col_dashboard:
    st.subheader("📊 GitInsight 실시간 분석")
    st.caption("LangGraph 에이전트가 코드를 분석하고 채점하는 실시간 현황판입니다.")

    tab_code, tab_report = st.tabs(["📂 검출된 기술 및 코드", "📝 평가 및 리포트"])

    with tab_code:
        st.write("### 🛠️ 검출된 프로젝트 기술 스택")
        if st.session_state.tech_stack:
            cols = st.columns(max(len(st.session_state.tech_stack), 1))
            for i, tech in enumerate(st.session_state.tech_stack):
                cols[i].info(f"**{tech}**")
        else:
            st.info("코드를 파싱하기 전입니다. 첫 대화가 시작되면 자동으로 채워집니다.")

        st.write("---")

        st.write("### 📂 RAG 기반 핵심 소스코드")
        current_hl = st.session_state.get("current_highlight", None)

        if st.session_state.extracted_chunks:
            for idx, chunk in enumerate(st.session_state.extracted_chunks):
                file_path = chunk.get("file_path", "unknown_file")

                is_target_file = False
                hl_start, hl_end = None, None
                if current_hl and current_hl.get("file_path") == file_path:
                    is_target_file = True
                    hl_start = current_hl.get("start_line")
                    hl_end = current_hl.get("end_line")

                expander_title = f"📄 [{idx+1}] {file_path}"
                if is_target_file:
                    expander_title += " 🔍 [면접관 지목 영역]"

                with st.expander(expander_title, expanded=is_target_file):
                    if is_target_file:
                        render_highlighted_code(chunk.get("content", ""), start_line=hl_start, end_line=hl_end)
                    else:
                        st.code(chunk.get("content", ""), language=chunk.get("language", "python"))
        else:
            st.info("질문과 밀접한 연관이 있는 핵심 파일이 검색되면 여기에 코드가 렌더링됩니다.")

    with tab_report:
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

        st.write("### 📝 최종 리팩토링 가이드")
        if st.session_state.final_report:
            st.markdown(st.session_state.final_report)
        else:
            st.info("면접의 전 과정이 완료되면 개선 가이드라인 리포트가 생성됩니다.")


# ==========================================
# 4. 사용자 채팅 및 백엔드 연동
# ==========================================
if prompt := st.chat_input("질문 혹은 답변을 입력하세요."):

    # 세션 상태에서 repo_url 읽기 (사이드바 입력값이 항상 보존됨)
    repo_url = st.session_state.repo_url

    st.session_state.messages.append({"role": "user", "content": prompt})
    with col_chat:
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            status_placeholder = st.empty()
            response_placeholder = st.empty()

            # 🔴 [치명적 버그 수정] FastAPI 라우터 프리픽스(/api/v1)를 추가하여 정확한 주소로 매핑
            backend_url = "http://127.0.0.1:8000/api/v1/chat/sync"

            payload = {
                "user_id": st.session_state.user_id,
                "user_answer": prompt,
                "current_retry_count": st.session_state.retry_count,
                "repo_url": repo_url if repo_url else None
            }

            status_placeholder.info("⚡ GitInsight 에이전트가 코드를 탐색하고 답변을 평가하는 중입니다...\n(최초 파일 임베딩 및 빌드 시에는 약 1~2분이 소요될 수 있으니 잠시만 기다려 주세요.)")

            try:
                response = requests.post(backend_url, json=payload, timeout=300)

                if response.status_code == 200:
                    status_placeholder.empty()
                    response_data = response.json()
                    result_data = response_data.get("data", {})

                    feedback = result_data.get("feedback", "")
                    next_q = result_data.get("next_question", "")
                    status_val = result_data.get("status", "")

                    # 상태별 채팅 메시지 구성
                    if status_val == "HINT":
                        # 힌트: evaluator 피드백(오답 이유) + extractor 힌트 메시지
                        if feedback and next_q:
                            ai_message = f"🔴 **오답 처리**\n\n{feedback}\n\n---\n\n{next_q}"
                        elif next_q:
                            ai_message = next_q
                        else:
                            ai_message = feedback
                    elif status_val == "REPORT":
                        ai_message = result_data.get("final_report", feedback) or feedback
                    elif next_q:
                        ai_message = f"{feedback}\n\n---\n\n**[다음 질문]**\n{next_q}" if feedback else next_q
                    else:
                        ai_message = feedback or "응답을 처리하는 중입니다."

                    # 백엔드가 리턴한 상태 세션에 동기화
                    st.session_state.retry_count = result_data.get("new_retry_count", 0)
                    st.session_state.current_highlight = result_data.get("highlight", None)
                    st.session_state.current_question = result_data.get("next_question", "")

                    if result_data.get("tech_stack"):
                        st.session_state.tech_stack = result_data["tech_stack"]
                    if result_data.get("extracted_chunks"):
                        st.session_state.extracted_chunks = result_data["extracted_chunks"]
                    if result_data.get("evaluation"):
                        st.session_state.evaluation = result_data["evaluation"]
                    if result_data.get("final_report"):
                        st.session_state.final_report = result_data["final_report"]

                    if result_data.get("status") == "REPORT":
                        st.session_state.current_question = ""
                        st.session_state.retry_count = 0

                    for word in ai_message.split(" "):
                        full_response = ""
                        full_response += word + " "
                        response_placeholder.markdown(full_response + "▌")
                        time.sleep(0.02)
                    response_placeholder.markdown(ai_message)
                    st.session_state.messages.append({"role": "assistant", "content": ai_message})
                    st.rerun()

                else:
                    status_placeholder.empty()
                    error_msg = f"⚠️ 서버 비정상 응답 (코드: {response.status_code})"
                    response_placeholder.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})

            except requests.exceptions.Timeout:
                status_placeholder.empty()
                error_msg = "⚠️ **요청 대기 시간 초과(Timeout)**\n\n지정한 대기 시간(5분) 내에 에이전트로부터 응답을 받지 못했습니다. 깃허브 저장소 용량이 크거나 서버의 LLM 네트워크 지연 때문일 수 있으니, 잠시 후 다시 시도해 보세요."
                response_placeholder.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

            except requests.exceptions.ConnectionError:
                status_placeholder.empty()
                error_msg = "⚠️ **백엔드 서버(포트 8000) 연결 거부**\n\n현재 로컬 백엔드 서버가 켜져 있지 않습니다. 터미널에서 백엔드를 가동해 주세요!"
                response_placeholder.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

            except Exception as e:
                status_placeholder.empty()
                error_msg = f"⚠️ **요청 처리 중 예기치 못한 에러 발생**\n\n에러 내용: `{str(e)}`"
                response_placeholder.error(error_msg)
                st.session_state.messages.append({"role": "assistant", "content": error_msg})

        st.session_state.answer_history.append(prompt)
        st.rerun()
