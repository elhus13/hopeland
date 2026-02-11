import uuid
import time
import base64

import streamlit as st
import anthropic
from openai import OpenAI
from pinecone import Pinecone
import docx


# ==========================================
# 1) 기본 설정
# ==========================================
st.set_page_config(page_title="NDTC Team HQ", page_icon="🏙️", layout="wide")


# ==========================================
# 2) 로그인
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

        submitted = st.form_submit_button("입장하기")  # ✅ 수정됨

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
index = pc.Index("ndtc-memory")  # Pinecone 인덱스 이름


# ==========================================
# 4) 카테고리(8개) + 설명
# ==========================================
CATEGORY_INFO = {
    "기술현황(Tech Scan)": "기술/툴/프로토콜 조사·요약·비교 자료",
    "시장/경쟁(Benchmark)": "유사 프로젝트·경쟁 사례 비교 분석",
    "규제/정책(Regulation)": "법·정책·규정·리스크 관련 조사",
    "공유회의(Sharing Meeting)": "중간 조사 공유·브레인스토밍 기록(결정 전)",
    "결정회의(Decision Meeting)": "확정된 방향·합의 내용 기록",
    "설계/아키텍처(Architecture)": "구조도·데이터/정산 흐름 등 시스템 설계 문서",
    "기획/문서(Planning Doc)": "제안서·피치덱·사업계획·로드맵 등 기획 산출물",
    "현장/증빙(Proof/Photos)": "사진·스캔·캡처 등 증빙·기록 자료",
}
CATEGORIES = list(CATEGORY_INFO.keys())


# ==========================================
# 5) 메뉴
# ==========================================
menu = st.sidebar.radio("업무 선택", ["AI 전략 비서 (Chat)", "지식 도서관 (자료 저장)", "대시보드"])


# ==========================================
# 6) AI 전략 비서 (Chat)
# ==========================================
if menu == "AI 전략 비서 (Chat)":
    st.header("🤖 NDTC 수석 전략가 '엘투르'")

    system_context = """
당신은 'NDTC(No Dealer Trading City Center)'의 수석 AI 전략가이며, 엘후스님의 개인 비서 '엘투르'입니다.

- 교육자: 기술 개념을 쉽게 설명
- 분석가: 업로드된 내부 자료를 근거로 적용점 제안
- 파트너: 객관적인 분별 제공

규칙:
- 참고할 내부 자료가 있으면 우선 활용
- 답변은 정중하고 논리적
""".strip()

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "엘투르입니다. 오늘은 어떤 전략을 논의할까요?"}]

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    user_text = st.chat_input("질문하거나 명령을 내려주세요...")
    if user_text:
        st.session_state.messages.append({"role": "user", "content": user_text})
        with st.chat_message("user"):
            st.markdown(user_text)

        knowledge_text = ""
        used_files = []

        try:
            q_emb = oai.embeddings.create(model="text-embedding-3-small", input=user_text)
            q_vec = q_emb.data[0].embedding
            res = index.query(vector=q_vec, top_k=3, include_metadata=True)

            chunks = []
            for m in res.get("matches", []):
                if m.get("score", 0) > 0.7:
                    md = m.get("metadata", {}) or {}
                    chunks.append(md.get("text", ""))
                    used_files.append(md.get("filename", "unknown"))

            if chunks:
                knowledge_text = "\n\n".join([c for c in chunks if c])

        except Exception:
            knowledge_text = ""

        final_user = f"""사용자 질문:
{user_text}

[참고할 내부 자료]
{knowledge_text if knowledge_text else "관련 내부 자료 없음. 일반 지식으로 답변."}
"""

        with st.chat_message("assistant"):
            try:
                resp = claude.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=2000,
                    system=system_context,
                    messages=[{"role": "user", "content": final_user}],
                )
                answer = resp.content[0].text

                if used_files:
                    answer += "\n\n---\n📚 참고 파일:\n" + "\n".join([f"- {f}" for f in sorted(set(used_files))])

                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})

            except Exception as e:
                st.error(f"오류: {e}")


# ==========================================
# 7) 지식 도서관 (멀티 업로드 + 옆 설명)
# ==========================================
elif menu == "지식 도서관 (자료 저장)":
    st.header("📚 NDTC 지식 저장소")
    st.info("여러 파일을 한 번에 선택해서, 같은 카테고리로 일괄 저장합니다.")

    with st.form("upload_form", clear_on_submit=False):

    uploaded_files = st.file_uploader(
        "파일 선택 (여러 개 가능)",
        type=["pdf", "txt", "docx", "png", "jpg", "jpeg"],
        accept_multiple_files=True
    )

    def category_label(opt):
        return f"{opt}  —  {CATEGORY_INFO[opt]}"

    category = st.selectbox(
        "자료 분류 (설명 포함)",
        CATEGORIES,
        index=0,
        format_func=category_label
    )

    st.caption(f"🧾 선택된 분류 설명: {CATEGORY_INFO[category]}")

    saved = st.form_submit_button("💾 선택한 파일 모두 저장하기")

       
    if saved:
        if not uploaded_files:
            st.warning("파일을 선택해 주세요.")
            st.stop()

        ok_count, fail_count = 0, 0

        for uploaded_file in uploaded_files:
            with st.spinner(f"저장 중: {uploaded_file.name}"):
                try:
                    raw_text = ""
                    ext = uploaded_file.name.split(".")[-1].lower()

                    if ext == "pdf":
                        import PyPDF2
                        reader = PyPDF2.PdfReader(uploaded_file)
                        for page in reader.pages:
                            raw_text += (page.extract_text() or "") + "\n"

                    elif ext == "docx":
                        doc = docx.Document(uploaded_file)
                        raw_text = "\n".join([p.text for p in doc.paragraphs])

                    elif ext == "txt":
                        raw_text = uploaded_file.read().decode("utf-8", errors="ignore")

                    elif ext in ["png", "jpg", "jpeg"]:
                        img_bytes = uploaded_file.getvalue()
                        b64_img = base64.b64encode(img_bytes).decode("utf-8")
                        data_url = f"data:image/jpeg;base64,{b64_img}"

                        vision = oai.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[{
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "이 이미지가 담고 있는 내용을 업무 기록용으로 상세히 텍스트로 설명해줘."},
                                    {"type": "image_url", "image_url": {"url": data_url}},
                                ],
                            }],
                        )
                        raw_text = (vision.choices[0].message.content or "").strip()

                    if not raw_text.strip():
                        st.warning(f"⚠️ 내용 추출 실패: {uploaded_file.name}")
                        fail_count += 1
                        continue

                    emb = oai.embeddings.create(model="text-embedding-3-small", input=raw_text[:8000])
                    vec = emb.data[0].embedding
                    doc_id = str(uuid.uuid4())

                    index.upsert([
                        (doc_id, vec, {
                            "uploader": st.session_state.user_id,
                            "filename": uploaded_file.name,
                            "category": category,
                            "category_desc": CATEGORY_INFO[category],
                            "file_ext": ext,
                            "text": raw_text[:2000],
                        })
                    ])

                    ok_count += 1
                    st.success(f"✅ 저장 완료: {uploaded_file.name}")

                except Exception as e:
                    fail_count += 1
                    st.error(f"❌ 실패({uploaded_file.name}): {e}")

        st.info(f"📦 저장 결과: 성공 {ok_count}개 / 실패 {fail_count}개")


# ==========================================
# 8) 대시보드
# ==========================================
elif menu == "대시보드":
    st.header("📊 NDTC 프로젝트 현황")
    col1, col2, col3 = st.columns(3)
    col1.metric("현재 단계", "Phase 1", "기반 구축")
    col2.metric("지식 데이터", "Active", "Pinecone 연동")
    col3.metric("팀원", "5명", "All Active")
