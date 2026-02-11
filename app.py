import uuid
import time
import base64
import json

import streamlit as st
import anthropic
from openai import OpenAI
from pinecone import Pinecone
import docx

# ==========================================
# 기본 설정
# ==========================================
st.set_page_config(page_title="NDTC Team HQ", page_icon="🏙️", layout="wide")

# ==========================================
# 로그인
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = ""

def login_page():
    st.title("🔒 NDTC 디지털 본부 (Hopeland)")
    st.write("관계자 외 출입금지")

    with st.form("login_form"):
        col1, col2 = st.columns(2)

        with col1:
            user_id = st.text_input("아이디 (ID)")
        with col2:
            password = st.text_input("비밀번호 (PW)", type="password")

        submitted = st.form_submit_button("입장하기")  # ✅ 수정됨

        if submitted:
            valid_users = st.secrets.get("passwords", {"admin": "1234"})
            if user_id in valid_users and valid_users[user_id] == password:
                st.session_state.logged_in = True
                st.session_state.user_id = user_id
                st.success(f"환영합니다, {user_id}님!")
                time.sleep(0.3)
                st.rerun()
            else:
                st.error("🚫 접근 승인 거부")

if not st.session_state.logged_in:
    login_page()
    st.stop()

# ==========================================
# API 설정
# ==========================================
anthropic_key = st.secrets["ANTHROPIC_API_KEY"]
pinecone_key = st.secrets["PINECONE_API_KEY"]
openai_key = st.secrets["OPENAI_API_KEY"]

claude = anthropic.Anthropic(api_key=anthropic_key)
oai = OpenAI(api_key=openai_key)
pc = Pinecone(api_key=pinecone_key)
index = pc.Index("ndtc-memory")

st.sidebar.success(f"👤 접속자: {st.session_state.user_id}")
menu = st.sidebar.radio("업무 선택", ["AI 전략 비서", "지식 도서관", "대시보드"])

# ==========================================
# 카테고리 정의
# ==========================================
CATEGORY_INFO = {
    "기술현황(Tech Scan)": "기술/툴/프로토콜 조사·요약·비교 자료",
    "시장/경쟁(Benchmark)": "유사 프로젝트·경쟁 사례 비교 분석",
    "규제/정책(Regulation)": "법·정책·규정·리스크 관련 조사",
    "공유회의(Sharing Meeting)": "중간 조사 공유·브레인스토밍 기록",
    "결정회의(Decision Meeting)": "확정된 방향·합의 내용 기록",
    "설계/아키텍처(Architecture)": "구조도·데이터·정산 흐름 설계 문서",
    "기획/문서(Planning Doc)": "제안서·피치덱·사업계획·로드맵",
    "현장/증빙(Proof/Photos)": "사진·스캔·캡처 등 증빙 자료"
}
CATEGORIES = list(CATEGORY_INFO.keys())

# ==========================================
# 지식 도서관
# ==========================================
if menu == "지식 도서관":

    st.header("📚 NDTC 지식 저장소")

    with st.form("upload_form"):

        uploaded_files = st.file_uploader(
            "파일 선택 (여러 개 가능)",
            type=["pdf", "txt", "docx"]()
