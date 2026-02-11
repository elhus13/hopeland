import streamlit as st
import anthropic
from openai import OpenAI
from pinecone import Pinecone
import uuid
import time
import base64
import docx
import io
from PIL import Image

# ==========================================
# 1. 기본 설정
# ==========================================
st.set_page_config(page_title="NDTC Team HQ", page_icon="🏙️", layout="wide")

# ==========================================
# 2. 로그인 시스템
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = ""

def login():
    st.title("🔒 NDTC 디지털 본부 (Hopeland)")
    st.write("관계자 외 출입금지")

    with st.form("login_form"):
        col1, col2 = st.columns(2)

        with col1:
            user_id = st.text_input("아이디 (ID)")

        with col2:
            password = st.text_input("비밀번호 (PW)", type="password")

        submitted = st.form_submit_button("출근하기")

        if submitted:
            valid_users = st.secrets.get(
                "passwords",
                {"admin": "1234", "team": "ndtc2026"}
            )

            if user_id in valid_users and valid_users[user_id] == password:
                st.session_state.logged_in = True
                st.session_state.user_id = user_id
                st.success(f"환영합니다, {user_id}님!")
                time.sleep(0.5)
                st.rerun()
            else:
                st.error("🚫 접근 승인이 거부되었습니다.")

if not st.session_state.logged_in:
    login()
    st.stop()

# ==========================================
# 3. 시스템 초기화
# ==========================================
st.sidebar.success(f"👤 접속자: {st.session_state.user_id}")
st.title("🏙️ NDTC 디지털 본부 (Hopeland)")
st.caption("AI & Blockchain 기반 무딜러 유통 혁신 플랫폼")

# API 키 로드
try:
    anthropic_key = st.secrets["ANTHROPIC_API_KEY"]
    pinecone_key = st.secrets["PINECONE_API_KEY"]
    openai_key = st.secrets["OPENAI_API_KEY"]
except:
    st.error("⚠️ API 키 설정 오류")
    st.stop()

# 클라이언트 생성 (안정형 SDK)
client = anthropic.Anthropic(api_key=anthropic_key)
oai = OpenAI(api_key=openai_key)
pc = Pinecone(api_key=pinecone_key)
index = pc.Index("ndtc-memory")

menu = st.sidebar.radio(
    "업무 선택",
    ["AI 전략 비서 (Chat)", "지식 도서관 (자료 저장)", "대시보드"]
)

# ==========================================
# 4. AI 전략 비서
# ==========================================
if menu == "AI 전략 비서 (Chat)":

    st.header("🤖 NDTC 수석 전략가 '엘투르'")

    if "messages" not in st.session_state:
