# app.py
import uuid
import time
import base64
import io

import streamlit as st
import anthropic
from openai import OpenAI
from pinecone import Pinecone
import docx
from PIL import Image

# PDF 텍스트 추출 (pypdf 권장)
try:
    from pypdf import PdfReader
except Exception:
    PdfReader = None


# =========================
# 0) 기본 설정
# =========================
st.set_page_config(page_title="NDTC Team HQ", page_icon="🏙️", layout="wide")


# =========================
# 1) 카테고리 (한 칸에 설명 포함)
# =========================
CATEGORY_INFO = {
    "기술현황(Tech Scan)": "기술/툴/프로토콜 조사, 요약, 비교 자료",
    "시장/경쟁(Benchmark)": "경쟁사/유사 프로젝트, 사례 비교",
    "규제/정책(Regulation)": "법/정책/규정/리스크 분석",
    "공유회의(Sharing Meeting)": "중간 조사 공유, 브레인스토밍, 논의 기록(결정 전)",
    "결정회의(Decision Meeting)": "무엇을 하기로 했다가 명확한 확정 회의 기록",
    "설계/아키텍처(Architecture)": "구조도, 흐름, 데이터/결제/정산 설계 문서",
    "기획/문서(Planning Doc)": "제안서/피치덱/사업계획/로드맵 등 기획문서",
    "현장/증빙(Proof/Photos)": "사진/스캔/증빙/캡처 등 증거 자료",
}
CATEGORIES = list(CATEGORY_INFO.keys())


# =========================
# 2) 로그인
# =========================
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False
    st.session_state.user_id = ""


def login_screen():
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
                time.sleep(0.4)
                st.rerun()
            else:
                st.error("🚫 접근 승인이 거부되었습니다.")


if not st.session_state.logged_in:
    login_screen()
    st.stop()


# =========================
# 3) API 키 / 클라이언트 로드
# =========================
st.sidebar.success(f"👤 접속자: {st.session_state.user_id}")
st.title("🏙️ NDTC 디지털 본부 (Hopeland)")
st.caption("AI & Blockchain 기반 무딜러 유통 혁신 플랫폼")

try:
    anthropic_key = st.secrets["ANTHROPIC_API_KEY"]
    pinecone_key = st.secrets["PINECONE_API_KEY"]
    openai_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    st.error("⚠️ API 키 설정 오류: Streamlit Secrets에 키가 있는지 확인하세요.")
    st.stop()

# Anthropic
anthropic_client = anthropic.Anthropic(api_key=anthropic_key)

# OpenAI (안정형 클라이언트 방식)
oai = OpenAI(api_key=openai_key)

# Pinecone
pc = Pinecone(api_key=pinecone_key)

# 인덱스 이름은 Secrets에서 바꾸기 쉽게
INDEX_NAME = st.secrets.get("PINECONE_INDEX", "ndtc-memory")
index = pc.Index(INDEX_NAME)


# =========================
# 4) 메뉴
# =========================
menu = st.sidebar.radio("업무 선택", ["AI 전략 비서 (Chat)", "지식 도서관 (자료 저장)", "대시보드"])


# =========================
# 5) 공통 유틸
# =========================
def safe_pdf_text(file_obj) -> str:
    """PDF에서 텍스트 추출"""
    if PdfReader is None:
        return ""
    try:
        reader = PdfReader(file_obj)
        texts = []
        for page in reader.pages:
            t = page.extract_text() or ""
            if t.strip():
                texts.append(t)
        return "\n".join(texts)
    except Exception:
        return ""


def docx_text(file_obj) -> str:
    """DOCX 텍스트 추출"""
    try:
        d = docx.Document(file_obj)
        return "\n".join([p.text for p in d.paragraphs if p.text.strip()])
    except Exception:
        return ""


def txt_text(file_obj) -> str:
    """TXT 텍스트 추출"""
    try:
        return file_obj.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def image_to_text(uploaded_file) -> str:
    """이미지 → 비전 모델로 설명 텍스트 생성"""
    try:
        img_bytes = uploaded_file.getvalue()
        b64 = base64.b64encode(img_bytes).decode("utf-8")

        resp = oai.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": "이 이미지가 담고 있는 내용을 상세히 텍스트로 설명해줘."},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                    ],
                }
            ],
        )
        return resp.choices[0].message.content or ""
    except Exception:
        return ""


def make_embedding(text: str):
    """텍스트 임베딩 생성"""
    resp = oai.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],  # 너무 길면 잘라서
    )
    return resp.data[0].embedding


def upsert_to_pinecone(*, vector, filename, category, raw_text):
    """Pinecone에 저장"""
    doc_id = str(uuid.uuid4())  # 안전한 ID
    index.upsert(
        vectors=[
            {
                "id": doc_id,
                "values": vector,
                "metadata": {
                    "uploader": st.session_state.user_id,
                    "filename": filename,
                    "category": category,
                    "text": raw_text[:2000],  # metadata 용량 고려
                    "created_at": int(time.time()),
                },
            }
        ]
    )
    return doc_id


# =========================
# 6) AI 전략 비서 (Chat)
# =========================
if menu == "AI 전략 비서 (Chat)":
    st.header("🤖 NDTC 수석 전략가 '엘투르'")

    system_context = """
당신은 'NDTC(No Dealer Trading City Center)'의 수석 AI 전략가이자, 엘후스님의 개인 비서 '엘투르'입니다.

[우리의 핵심 사업]
1. 프로젝트명: 리플(XRP) 기반 글로벌 유통 도시 건설 및 플랫폼 구축
2. 목표: 블록체인과 AI 기술을 활용한 물류/유통 혁신 도시 설계
3. 핵심 기술: XRP Ledger, 자체 토큰(유틸리티) 발행 및 상장, RWA 발행
4. 현재 상태: 학습 및 기획 단계

[당신의 역할]
1. 교육자: 기술 개념을 쉽게 설명
2. 분석가: 업로드 자료 분석 및 적용점 제안
3. 파트너: 무조건적 응원보다 객관적 분별 제공

[규칙]
- 내부 자료가 있으면 우선 근거로 사용
- 답변은 정중하고 논리적으로
"""

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "엘투르입니다. 오늘은 어떤 전략을 논의할까요?"}]

    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    prompt = st.chat_input("질문하거나 명령을 내려주세요...")
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # RAG 검색
        knowledge_text = ""
        sources = []

        try:
            q_vec = make_embedding(prompt)
            res = index.query(vector=q_vec, top_k=3, include_metadata=True)
            for match in res.get("matches", []):
                score = match.get("score", 0)
                meta = match.get("metadata", {}) or {}
                if score >= 0.70 and meta.get("text"):
                    sources.append(meta.get("filename", "unknown"))
                    knowledge_text += f"\n- ({meta.get('filename','unknown')}) {meta.get('text','')}"
        except Exception:
            pass

        final_prompt = f"""{prompt}

[참고할 우리 팀 내부 자료]
{knowledge_text if knowledge_text.strip() else "관련된 내부 자료가 없습니다. 일반 지식으로 답변하세요."}
"""

        with st.chat_message("assistant"):
            try:
                resp = anthropic_client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=2000,
                    system=system_context,
                    messages=[
                        {"role": "user", "content": final_prompt}
                    ],
                )
                answer = resp.content[0].text

                if sources:
                    uniq = []
                    for s in sources:
                        if s not in uniq:
                            uniq.append(s)
                    answer += "\n\n---\n📚 참고한 내부 자료:\n" + "\n".join([f"- {x}" for x in uniq])

                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")


# =========================
# 7) 지식 도서관 (자료 저장)
# =========================
elif menu == "지식 도서관 (자료 저장)":
    st.header("📚 NDTC 지식 저장소")
    st.info("여러 파일을 한 번에 선택하고, 같은 카테고리로 일괄 저장할 수 있습니다.")

    def category_label(opt: str) -> str:
        return f"{opt} — {CATEGORY_INFO.get(opt, '')}"

    with st.form("upload_form", clear_on_submit=False):
        uploaded_files = st.file_uploader(
            "파일 선택 (여러 개 가능)",
            type=["pdf", "txt", "docx", "png", "jpg", "jpeg"],
            accept_multiple_files=True,
        )

        category = st.selectbox(
            "자료 분류 (설명 포함)",
            CATEGORIES,
            index=0,
            format_func=category_label,
        )

        st.caption(f"선택된 분류 설명: {CATEGORY_INFO[category]}")
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

                    # 문서 처리
                    if ext == "pdf":
                        raw_text = safe_pdf_text(uploaded_file)
                        if not raw_text.strip():
                            raw_text = "(PDF 텍스트 추출 실패: 스캔 PDF일 수 있습니다.)"

                    elif ext == "docx":
                        raw_text = docx_text(uploaded_file)

                    elif ext == "txt":
                        raw_text = txt_text(uploaded_file)

                    # 이미지 처리(비전)
                    elif ext in ["png", "jpg", "jpeg"]:
                        raw_text = image_to_text(uploaded_file)
                        if raw_text.strip():
                            st.info(f"🖼️ 이미지 분석 요약: {raw_text[:120]}...")

                    if not raw_text.strip():
                        fail_count += 1
                        st.warning(f"내용을 읽을 수 없어 저장하지 못했습니다: {uploaded_file.name}")
                        continue

                    vec = make_embedding(raw_text)
                    upsert_to_pinecone(
                        vector=vec,
                        filename=uploaded_file.name,
                        category=category,
                        raw_text=raw_text,
                    )
                    ok_count += 1

                except Exception as e:
                    fail_count += 1
                    st.error(f"업로드 실패: {uploaded_file.name} / {e}")

        st.success(f"✅ 저장 완료! 성공 {ok_count}개 / 실패 {fail_count}개")


# =========================
# 8) 대시보드
# =========================
elif menu == "대시보드":
    st.header("📊 NDTC 프로젝트 현황")
    st.write("팀원들과 공유할 공지사항이나 현황판입니다.")

    col1, col2, col3 = st.columns(3)
    col1.metric("현재 단계", "Phase 1", "기반 구축")
    col2.metric("지식 데이터", "Ready", "Pinecone 연동됨")
    col3.metric("팀원", "5명", "All Active")
