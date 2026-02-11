# app.py  (NDTC Hopeland - Full Replace)

import uuid
import time
import base64

import streamlit as st
import anthropic
from openai import OpenAI
from pinecone import Pinecone
import docx
from PIL import Image  # noqa: F401


# ==========================================
# 1) 기본 설정
# ==========================================
st.set_page_config(page_title="NDTC Team HQ", page_icon="🏙️", layout="wide")


# ==========================================
# 2) 로그인 (간단)
# ==========================================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
if "user_id" not in st.session_state:
    st.session_state.user_id = ""


def login_page() -> None:
    st.title("🔒 NDTC 디지털 본부 (Hopeland)")
    st.write("관계자 외 출입금지")

    with st.form("login_form", clear_on_submit=False):
        col1, col2 = st.columns(2)
        with col1:
            user_id = st.text_input("아이디 (ID)")
        with col2:
            password = st.text_input("비밀번호 (PW)", type="password")

        submitted = st.form_submit_button("출근하기")

        if submitted:
            valid_users = st.secrets.get("passwords", {"admin": "1234", "team": "ndtc2026"})
            if user_id in valid_users and valid_users[user_id] == password:
                st.session_state.logged_in = True
                st.session_state.user_id = user_id
                st.success(f"환영합니다, {user_id}님!")
                time.sleep(0.3)
                st.rerun()
            else:
                st.error("🚫 접근 승인이 거부되었습니다.")


if not st.session_state.logged_in:
    login_page()
    st.stop()


# ==========================================
# 3) API 키 / 클라이언트
# ==========================================
st.sidebar.success(f"👤 접속자: {st.session_state.user_id}")
st.title("🏙️ NDTC 디지털 본부 (Hopeland)")
st.caption("AI & Blockchain 기반 무딜러 유통 혁신 플랫폼")

try:
    anthropic_key = st.secrets["ANTHROPIC_API_KEY"]
    pinecone_key = st.secrets["PINECONE_API_KEY"]
    openai_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    st.error("⚠️ Secrets에 API 키가 없습니다. (OPENAI/ANTHROPIC/PINECONE)")
    st.stop()

claude = anthropic.Anthropic(api_key=anthropic_key)
oai = OpenAI(api_key=openai_key)

pc = Pinecone(api_key=pinecone_key)
index = pc.Index("ndtc-memory")  # Pinecone 인덱스 이름(이미 생성되어 있어야 함)


# ==========================================
# 4) 카테고리(요청하신 9개) + 설명
# ==========================================
CATEGORY_INFO = {
    "기술현황(Tech
