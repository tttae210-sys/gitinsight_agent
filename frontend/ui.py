import streamlit as st
import time
import requests
import json
import io
import os

# Docker/로컬 환경 모두 대응: 환경변수 API_BASE_URL이 있으면 그것을 사용, 없으면 로컬 기본값
API_BASE_URL = os.environ.get("API_BASE_URL", "http://127.0.0.1:8000/api/v1")

# ==========================================
# 0. PDF 이력서 파싱 라이브러리 및 어댑터
# ==========================================
try:
    import pypdf
    PYPDF_AVAILABLE = True
except ImportError:
    PYPDF_AVAILABLE = False


def extract_text_from_pdf(uploaded_file) -> str:
    """업로드된 PDF 파일 버퍼를 읽어와 텍스트를 추출합니다."""
    if not PYPDF_AVAILABLE:
        return (
            "⚠️ 'pypdf' 라이브러리가 설치되지 않아 텍스트 추출이 불가능합니다.\n"
            "터미널에서 'pip install pypdf' 명령어로 설치 후 다시 업로드해 주세요!\n"
            "임시로 파일 메타데이터(파일명) 정보만 기록합니다."
        )
    try:
        pdf_file = io.BytesIO(uploaded_file.getvalue())
        reader = pypdf.PdfReader(pdf_file)
        text = ""
        for page in reader.pages:
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
        return text.strip()
    except Exception as e:
        return f"⚠️ PDF 파싱 과정에서 예외가 발생했습니다: {str(e)}"


# ==========================================
# 0-2. 커스텀 형광펜 렌더링 함수 (마크다운 충돌 우회 수정 완료)
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
            font-family: 'SF Mono', 'Monaco', 'Inconsolata', 'Roboto Mono', 'Consolas', monospace;
            font-size: 13px;
            line-height: 1.6;
            padding: 20px;
            border-radius: 12px;
            overflow-x: auto;
            border: 1px solid #30363d;
            box-shadow: 0 4px 8px rgba(0, 0, 0, 0.3);
            margin: 10px 0;
        }
        .code-line { 
            display: flex; 
            width: 100%; 
            transition: background-color 0.2s ease;
            min-height: 20px;
            align-items: center;
        }
        .code-line:hover {
            background-color: rgba(56, 139, 253, 0.1);
        }
        .line-number {
            color: #8b949e;
            text-align: right;
            width: 45px;
            padding-right: 12px;
            user-select: none;
            border-right: 1px solid #30363d;
            font-weight: 500;
            font-size: 12px;
        }
        .line-content { 
            padding-left: 12px; 
            white-space: pre-wrap;
            word-break: break-word;
            flex: 1;
        }
        .highlighted {
            background: linear-gradient(90deg, rgba(255, 193, 7, 0.15) 0%, rgba(255, 193, 7, 0.05) 100%);
            border-left: 4px solid #ffc107;
            animation: highlight-pulse 2s ease-in-out;
            box-shadow: inset 0 0 0 1px rgba(255, 193, 7, 0.2);
        }
        .highlighted .line-number {
            color: #ffc107;
            font-weight: 600;
        }
        .highlighted .line-content {
            color: #ffffff;
        }
        @keyframes highlight-pulse {
            0% { background: rgba(255, 193, 7, 0.3); }
            50% { background: rgba(255, 193, 7, 0.15); }
            100% { background: rgba(255, 193, 7, 0.15); }
        }
        .highlight-marker {
            position: absolute;
            right: 10px;
            color: #ffc107;
            font-size: 16px;
            font-weight: bold;
        }
        .code-header {
            background-color: #161b22;
            color: #f0f6fc;
            padding: 8px 15px;
            border-radius: 8px 8px 0 0;
            font-size: 12px;
            font-weight: 500;
            border-bottom: 1px solid #30363d;
            margin-bottom: 0;
        }
    </style>
    """

    # 문자열로 들어오는 경우를 위한 방어적 정수 캐스팅
    try:
        s_line = int(start_line) if start_line is not None else None
        e_line = int(end_line) if end_line is not None else None
    except ValueError:
        s_line, e_line = None, None

    # 하이라이트 범위가 있으면 헤더 추가
    if s_line is not None and e_line is not None:
        html_lines.append(f'<div class="code-header">🔍 면접관 지목 영역: {s_line}~{e_line}번째 줄</div>')

    html_lines.append('<div class="code-container">')
    
    highlight_count = 0
    for idx, line in enumerate(lines, 1):
        # HTML 특수 문자 이스케이프
        safe_line = (line.replace("&", "&amp;")
                        .replace("<", "&lt;")
                        .replace(">", "&gt;")
                        .replace('"', "&quot;")
                        .replace("'", "&#x27;"))
        
        is_highlighted = (
            s_line is not None and e_line is not None and s_line <= idx <= e_line
        )
        
        if is_highlighted:
            highlight_count += 1
            line_class = "code-line highlighted"
            marker = f'<span class="highlight-marker">📍</span>'
        else:
            line_class = "code-line"
            marker = ""
        
        # 빈 줄 처리
        line_content_val = safe_line if safe_line.strip() != "" else " "
        
        html_line = (f'<div class="{line_class}" style="position: relative;">'
                    f'<div class="line-number">{idx}</div>'
                    f'<div class="line-content">{line_content_val}</div>'
                    f'{marker}</div>')
        html_lines.append(html_line)
        
    html_lines.append('</div>')
    
    # 하이라이트된 줄 수 표시
    if highlight_count > 0:
        html_lines.append(f'<div style="text-align: center; margin-top: 10px; color: #ffc107; font-size: 12px;">✨ {highlight_count}줄이 하이라이트되었습니다</div>')
    
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
    st.session_state.user_id = "면접자"
if "retry_count" not in st.session_state:
    st.session_state.retry_count = 0
if "current_highlight" not in st.session_state:
    st.session_state.current_highlight = None
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "안녕하세요, 면접자님! GitInsight 모의 면접 튜터입니다. 분석을 원하시는 GitHub Repository URL을 왼쪽에 입력하고 이력서를 함께 등록하여 면접을 시작해 보세요!"}
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
    st.session_state.repo_url = ""       
if "resume_text" not in st.session_state:
    st.session_state.resume_text = ""
if "resume_name" not in st.session_state:
    st.session_state.resume_name = ""


# ==========================================
# 2. 사이드바 UI
# ==========================================
with st.sidebar:
    # 🚀 면접 시작 버튼을 맨 위에 배치
    st.header("🚀 면접 시작")
    if st.button("🎯 면접 시작", use_container_width=True):
        # GitHub URL 확인
        repo_url = st.session_state.get("repo_url", "").strip()
        if not repo_url:
            st.error("⚠️ GitHub Repository URL을 먼저 입력해주세요!")
            st.stop()
        
        # 1. 백엔드 LangGraph 스레드 상태 리셋 (이전 면접 상태 완전 제거)
        try:
            requests.post(
                f"{API_BASE_URL}/chat/reset",
                json={"user_id": st.session_state.user_id},
                timeout=10,
            )
        except Exception:
            pass  # 백엔드 리셋 실패해도 프론트엔드는 초기화 진행

        # 2. 프론트엔드 세션 초기화 (메시지는 비워둠)
        st.session_state.messages = []
        st.session_state.tech_stack = []
        st.session_state.extracted_chunks = []
        st.session_state.evaluation = {}
        st.session_state.final_report = ""
        st.session_state.retry_count = 0
        st.session_state.current_highlight = None
        st.session_state.answer_history = []
        st.session_state.resume_text = ""
        st.session_state.resume_name = ""
        
        # 3. 첫 질문 요청을 위한 더미 입력 처리
        with st.spinner("🤖 AI 면접관이 첫 질문을 준비하고 있습니다..."):
            backend_url = f"{API_BASE_URL}/chat/sync"
            payload = {
                "user_id": st.session_state.user_id,
                "user_answer": "질문해줢",  # 첫 질문 요청
                "current_retry_count": 0,
                "repo_url": repo_url,
                "resume_text": st.session_state.get("resume_text", None),
                "target_company": st.session_state.get("target_company", None),
                "target_field": st.session_state.get("target_field", None),
                "company_values": st.session_state.get("company_values", None)
            }
            
            try:
                response = requests.post(backend_url, json=payload, timeout=120)
                if response.status_code == 200:
                    response_data = response.json()
                    result_data = response_data.get("data", {})
                    
                    first_question = result_data.get("next_question", "")
                    if first_question:
                        # 첫 질문을 바로 메시지에 추가
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": f"**[첫 번째 질문]**\n{first_question}"
                        })
                        
                        # 상태 정보 업데이트
                        st.session_state.retry_count = result_data.get("new_retry_count", 0)
                        st.session_state.current_highlight = result_data.get("highlight", None)
                        if result_data.get("tech_stack"):
                            st.session_state.tech_stack = result_data["tech_stack"]
                        if result_data.get("extracted_chunks"):
                            st.session_state.extracted_chunks = result_data["extracted_chunks"]
                    else:
                        st.session_state.messages.append({
                            "role": "assistant", 
                            "content": "면접 준비가 완료되었습니다. '질문해줘'라고 입력하여 첫 질문을 받아보세요!"
                        })
                else:
                    st.session_state.messages.append({
                        "role": "assistant", 
                        "content": "면접 시작 중 오류가 발생했습니다. 다시 시도해주세요."
                    })
            except Exception as e:
                st.session_state.messages.append({
                    "role": "assistant", 
                    "content": "면접 시작 중 네트워크 오류가 발생했습니다. 다시 시도해주세요."
                })
        
        # repo_url은 초기화하지 않음 (다시 입력하는 불편함 방지)
        st.rerun()
    
    st.markdown("**새로운 면접을 시작하려면 위 버튼을 먼저 눌러주세요!**")
    st.write("---")

    st.header("⚙️ 프로젝트 설정")
    st.markdown("분석할 GitHub 레포지토리 정보를 기입해 주세요.")

    repo_url_input = st.text_input(
        "GitHub Repository URL",
        value=st.session_state.repo_url,
        key="repo_url_input_widget",
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

    # 🏢 목표 회사 및 분야 설정
    st.header("🏢 면접 목표 설정")
    st.markdown("목표 회사와 분야를 설정하면 해당 기업 스타일에 맞춘 면접 질문이 제공됩니다.")
    
    # 세션 상태 초기화 (새로 추가된 필드들)
    if "target_company" not in st.session_state:
        st.session_state.target_company = ""
    if "target_field" not in st.session_state:
        st.session_state.target_field = ""
    if "company_values" not in st.session_state:
        st.session_state.company_values = ""
    
    # 목표 회사 선택 (드롭다운으로 변경)
    company_options = [
        "", "카카오", "네이버", "쿠팡", "토스", "업스테이지(세계 최고 기업)", "라인", "배달의민족", 
        "당근마켓", "우아한형제들", "직접입력"
    ]
    
    selected_company = st.selectbox(
        "목표 회사",
        options=company_options,
        index=0 if not st.session_state.target_company else (
            company_options.index(st.session_state.target_company) 
            if st.session_state.target_company in company_options 
            else company_options.index("직접입력")
        ),
        help="지원하고자 하는 회사를 선택하세요. 해당 회사의 면접 스타일과 인재상을 반영합니다."
    )
    
    # 직접입력 선택 시 텍스트 입력창 표시
    if selected_company == "직접입력":
        custom_company = st.text_input(
            "회사명 직접 입력",
            placeholder="예: 스타트업명, 기타 회사...",
            help="목록에 없는 회사명을 직접 입력하세요."
        )
        st.session_state.target_company = custom_company
    else:
        # "업스테이지(세계 최고 기업)" 선택 시 "업스테이지"로 정규화
        normalized_company = selected_company.replace("(세계 최고 기업)", "").strip()
        st.session_state.target_company = normalized_company
    
    # 목표 분야/직군 선택 (옵션 확장)
    target_field = st.selectbox(
        "목표 분야/직군",
        options=["", "백엔드 개발", "프론트엔드 개발", "풀스택 개발", "DevOps/인프라", 
                "데이터 엔지니어", "ML/AI 엔지니어", "모바일 앱 개발", "게임 개발", 
                "블록체인 개발", "임베디드 개발", "QA/테스트", "기술 리드/아키텍트",
                "프로덕트 매니저", "UX/UI 디자이너"],
        index=0 if not st.session_state.target_field else 
              ["", "백엔드 개발", "프론트엔드 개발", "풀스택 개발", "DevOps/인프라", 
               "데이터 엔지니어", "ML/AI 엔지니어", "모바일 앱 개발", "게임 개발", 
               "블록체인 개발", "임베디드 개발", "QA/테스트", "기술 리드/아키텍트",
               "프로덕트 매니저", "UX/UI 디자이너"].index(st.session_state.target_field) if st.session_state.target_field in ["", "백엔드 개발", "프론트엔드 개발", "풀스택 개발", "DevOps/인프라", "데이터 엔지니어", "ML/AI 엔지니어", "모바일 앱 개발", "게임 개발", "블록체인 개발", "임베디드 개발", "QA/테스트", "기술 리드/아키텍트", "프로덕트 매니저", "UX/UI 디자이너"] else 0,
        help="지원하고자 하는 직군을 선택하세요. 해당 분야의 최신 트렌드가 반영된 전문 질문이 제공됩니다."
    )
    st.session_state.target_field = target_field
    
    # 선택된 회사의 인재상 자동 표시 (기업 데이터베이스에서 로드)
    if st.session_state.target_company and st.session_state.target_company in ["카카오", "네이버", "쿠팡", "토스", "업스테이지", "라인", "배달의민족", "당근마켓", "우아한형제들"]:
        st.info(f"**{st.session_state.target_company}** 인재상이 자동으로 적용됩니다 📋")
        # company_values는 자동으로 설정되므로 사용자 입력 불가
        st.session_state.company_values = f"auto:{st.session_state.target_company}"
    else:
        # 기업 인재상/핵심 가치 직접 입력 (사전 정의되지 않은 회사의 경우)
        company_values = st.text_area(
            "기업 인재상 / 핵심 가치",
            value=st.session_state.company_values if not st.session_state.company_values.startswith("auto:") else "",
            placeholder="예: 사용자 중심 사고, 빠른 실행력, 협업과 소통, 지속적 학습...",
            help="목표 회사의 인재상이나 핵심 가치를 입력하세요. 이를 바탕으로 문화적 핏을 확인하는 질문이 포함됩니다.",
            height=80,
            disabled=st.session_state.target_company in ["카카오", "네이버", "쿠팡", "토스", "업스테이지", "라인", "배달의민족", "당근마켓", "우아한형제들"]
        )
        if not st.session_state.company_values.startswith("auto:"):
            st.session_state.company_values = company_values
    
    # 설정 현황 요약 표시
    if st.session_state.target_company or target_field:
        with st.expander("🎯 현재 면접 목표 설정", expanded=False):
            if st.session_state.target_company:
                st.write(f"**목표 회사:** {st.session_state.target_company}")
                
                # 사전 정의된 회사의 경우 상세 정보 표시
                if st.session_state.target_company in ["카카오", "네이버", "쿠팡", "토스", "업스테이지", "라인", "배달의민족", "당근마켓", "우아한형제들"]:
                    st.write(f"**인재상:** 자동 적용됨 ✅")
                    st.write(f"**면접 스타일:** 해당 기업 맞춤형 ✅")
            if target_field:
                st.write(f"**목표 분야:** {target_field}")
                st.write(f"**최신 트렌드:** 자동 반영됨 🔥")

    st.write("---")

    # 📄 PDF 이력서 업로더
    st.header("📄 이력서 등록 (선택)")
    st.markdown("이력서를 등록하면 이력서 기재 역량과 실제 소스코드 간의 교차 검증 질문이 제공됩니다.")
    uploaded_file = st.file_uploader(
        "이력서 파일 업로드 (PDF)", type=["pdf"],
        help="이력서에 작성하신 성과와 깃허브 코드 간의 교차 검증을 위해 사용됩니다."
    )
    if uploaded_file is not None:
        if st.session_state.resume_name != uploaded_file.name:
            with st.spinner("📄 PDF 이력서에서 텍스트 데이터 추출 중..."):
                extracted_text = extract_text_from_pdf(uploaded_file)
                st.session_state.resume_text = extracted_text
                st.session_state.resume_name = uploaded_file.name
            st.success(f"✅ 분석 완료! ({uploaded_file.name})")
    else:
        st.session_state.resume_text = ""
        st.session_state.resume_name = ""

    st.write("---")

    # 🔴 3-Strike 힌트 현황 시각화
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


# ==========================================
# 3. 메인 화면 레이아웃 (채팅 + 대시보드)
# ==========================================
col_chat, col_dashboard = st.columns([1.1, 0.9], gap="large")

with col_chat:
    st.title("🤖 GitInsight")
    st.subheader("이력서 및 코드 기반 맞춤형 AI 면접관")
    st.write("지원자님의 이력서(주장)와 실제 구현 코드(증거)를 분석하여 날카로운 역량 검증 질문을 던집니다.")
    st.write("---")
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
                
                # 🔴 [정합성 버그 해결] 향상된 파일명 매칭 로직
                if current_hl and current_hl.get("file_path"):
                    target_file = current_hl.get("file_path").lower()
                    current_chunk_file = file_path.lower()
                    
                    # 다양한 매칭 방식으로 정확도 향상
                    is_exact_match = os.path.basename(target_file) == os.path.basename(current_chunk_file)
                    is_path_contains = target_file in current_chunk_file or current_chunk_file in target_file
                    is_filename_match = os.path.splitext(os.path.basename(target_file))[0] in current_chunk_file
                    
                    if is_exact_match or is_path_contains or is_filename_match:
                        is_target_file = True
                        hl_start = current_hl.get("start_line")
                        hl_end = current_hl.get("end_line")
                        
                        # 줄 번호 유효성 검사
                        total_lines = len(chunk.get("content", "").split("\n"))
                        if hl_start and hl_start > total_lines:
                            hl_start = max(1, total_lines - 5)  # 마지막 5줄 영역으로 조정
                        if hl_end and hl_end > total_lines:
                            hl_end = total_lines

                expander_title = f"📄 [{idx+1}] {file_path}"
                if is_target_file:
                    expander_title += " 🔥 [AI 면접관 포커스]"

                with st.expander(expander_title, expanded=is_target_file):
                    if is_target_file and hl_start and hl_end:
                        st.info(f"🎯 **면접 질문 관련 영역**: {hl_start}~{hl_end}번째 줄")
                        render_highlighted_code(chunk.get("content", ""), start_line=hl_start, end_line=hl_end)
                    elif is_target_file:
                        st.warning("⚠️ 하이라이트 정보가 부정확합니다. 전체 코드를 확인하세요.")
                        st.code(chunk.get("content", ""), language=chunk.get("language", "python"))
                    else:
                        st.code(chunk.get("content", ""), language=chunk.get("language", "python"))
        else:
            st.info("질문과 밀접한 연관이 있는 핵심 파일이 검색되면 여기에 코드가 렌더링됩니다.")

    with tab_report:
        # 🔴 면접 완료 후에도 오른쪽 사이드바에는 종합 리포트 표시하지 않음
        # 🔴 채팅창에서만 종합 리포트 확인 가능하도록 수정
        st.write("### 📋 현재 답변 평가")
        if st.session_state.evaluation:
            score = st.session_state.evaluation.get("score", "N/A")
            is_passed = st.session_state.evaluation.get("passed", False)
            metric_col1, metric_col2 = st.columns(2)
            metric_col1.metric("종합 점수", f"{score}점")
            if is_passed:
                metric_col2.metric("면접 결과", "✅ 합격")
            else:
                metric_col2.metric("면접 결과", "❌ 불합격")
            st.markdown(f"**상세 채점 기준:**\n{st.session_state.evaluation.get('reason', '')}")
        else:
            st.info("유저가 면접 질문에 답변을 완료하면 AI의 정밀 평가 결과가 실시간 기록됩니다.")
        
        # 🔴 면접 완료 시 안내 메시지만 표시 (종합 리포트는 채팅창에서만 확인)
        if st.session_state.final_report:
            st.write("---")
            st.info("🎉 면접이 완료되었습니다! 종합 평가 리포트는 채팅창에서 확인하세요.")


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

            backend_url = f"{API_BASE_URL}/chat/sync"

            payload = {
                "user_id": st.session_state.user_id,
                "user_answer": prompt,
                "current_retry_count": st.session_state.retry_count,
                "repo_url": repo_url if repo_url else None,
                "resume_text": st.session_state.resume_text if st.session_state.resume_text else None,
                "target_company": st.session_state.get("target_company", None),
                "target_field": st.session_state.get("target_field", None),
                "company_values": st.session_state.get("company_values", None)
            }

            # 에이전틱 진행 단계 시각화
            with st.status("AI 면접관이 답변을 심사하는 중입니다...", expanded=True) as status:
                st.write("🔍 1단계: GitHub 저장소의 최신 커밋 해시 추적 및 소스코드 탐색 중...")
                time.sleep(1.0)
                if st.session_state.resume_text:
                    st.write("📄 2단계: 이력서 기재 역량과 코드베이스 간의 상호 교차 대조 중...")
                    time.sleep(1.2)
                else:
                    st.write("📄 2단계: 이력서 데이터가 제공되지 않아 코드베이스 심층 분석 중...")
                    time.sleep(0.8)
                st.write("📚 3단계: 백엔드 아키텍처 및 면접 족보 DB 매칭 중...")
                time.sleep(1.0)
                st.write("🧠 4단계: 답변 내용 채점 및 튜터링 피드백 구성 중...")

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
                    if status_val == "PASS":
                        score = result_data.get("evaluation", {}).get("score", "")
                        score_text = f" ({score}점)" if score else ""
                        ai_message = f"✅ **면접 합격{score_text}**\n\n{feedback}"
                    elif status_val == "FAIL":
                        ai_message = f"{feedback}\n\n면접이 종료되었습니다. 우측 리포트 탭에서 상세 피드백을 확인하세요."
                    elif status_val in ("HINT", "HINT_GIVEN", "SURRENDER"):
                        # 🔴 힌트는 next_question에 이미 포함되어 있음 — feedback 무시
                        ai_message = next_q if next_q else "힌트 생성 중..."
                    elif status_val in ("ANSWER_GIVEN", "NEXT_QUESTION_DONE"):
                        # 🔴 정답 제공 후 자동으로 다음 질문으로 넘어감
                        if feedback and next_q:
                            ai_message = f"{feedback}\n\n---\n\n**[다음 질문]**\n{next_q}"
                        elif feedback:
                            ai_message = feedback
                        else:
                            ai_message = next_q or "다음 질문을 준비 중입니다..."
                    elif status_val == "REPORT":
                        ai_message = result_data.get("final_report", feedback) or feedback
                    elif next_q:
                        ai_message = f"{feedback}\n\n---\n\n**[다음 질문]**\n{next_q}" if feedback else next_q
                    else:
                        ai_message = feedback or "응답을 처리하는 중입니다."

                    # 🔴 [순서 교정] rerun() 실행 전 세션 기록과 대화 히스토리 완벽 바인딩 저장 처리
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

                    if status_val == "REPORT":
                        st.session_state.current_question = ""
                        st.session_state.retry_count = 0

                    st.session_state.answer_history.append(prompt)
                    st.session_state.messages.append({"role": "assistant", "content": ai_message})

                    # 응답 즉시 출력 (점진적 출력 효과 제거로 잘림 현상 방지)
                    response_placeholder.markdown(ai_message)
                    
                    # 모든 상태 저장 후에 리런 가동
                    st.rerun()

                else:
                    status_placeholder.empty()
                    error_msg = f"⚠️ 서버 비정상 응답 (코드: {response.status_code})"
                    response_placeholder.error(error_msg)
                    st.session_state.messages.append({"role": "assistant", "content": error_msg})

            except requests.exceptions.Timeout:
                status_placeholder.empty()
                error_msg = "⚠️ **요청 대기 시간 초과(Timeout)**\n\n지정한 대기 시간(5분) 내에 에이전트로부터 응답을 받지 못했습니다. 잠시 후 다시 시도해 주세요."
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