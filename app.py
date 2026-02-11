# app.py
import uuid
import time
import base64

import streamlit as st
import anthropic
from pinecone import Pinecone
import docx  # 워드 파일용
from PIL import Image  # noqa: F401 (PIL은 향후 이미지 처리 확장 대비)

# ✅ OpenAI 최신 권장 방식(클라이언트 객체)
from openai import OpenAI

# 1. 기본 설정
st.set_page_config(page_title="NDTC Team HQ", page_icon="🏙️", layout="wide")

# ==========================================
# [보안] 팀원 로그인 시스템
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

        submitted = st.form_submit_button("입장하기")

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
    login()
    st.stop()

# ==========================================
# [메인] 시스템 초기화
# ==========================================
st
