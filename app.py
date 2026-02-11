import uuid
import time
import base64

import streamlit as st
import anthropic
from openai import OpenAI
from pinecone import Pinecone
import docx

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
# 1) 카테고리 (지식 도서관 + 로그)
# =========================
CATEGORY_INFO = {
    # 리서치/현황
    "기술현황(Tech Scan)": "기술/툴/프로토콜 조사, 요약, 비교 자료",
    "시장/경쟁(Benchmark)": "경쟁사/유사 프로젝트, 사례 비교",
    "규제/정책(Regulation)": "법/정책/규정/리스크 분석",

    # 회의/공유
    "공유회의(Sharing Meeting)": "중간 조사 공유, 브레인스토밍, 논의 기록(결정 전)",
    "결정회의(Decision Meeting)": "무엇을 하기로 했다가 명확한 확정 회의 기록",

    # 설계/산출물
    "설계/아키텍처(Architecture)": "구조도, 흐름, 데이터/결제/정산 설계 문서",
    "기획/문서(Planning Doc)": "제안서/피치덱/사업계획/로드맵 등 기획문서",
    "현장/증빙(Proof/Photos)": "사진/스캔/증빙/캡처 등 증거 자료",

    # ✅ 로그(추가)
    "대화 업무로그": "팀 공유용: 대화 결과/결론/요약/핵심 산출물 기록",
    "대화 개인로그": "개인용: 접속 ID별 개인 기록(자동 분리 저장)",
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
                time.sleep(0.3)
                st.rerun()
            else:
                st.error("🚫 접근 승인이 거부되었습니다.")


if not st.session_state.logged_in:
    login_screen()
    st.stop()


# =========================
# 3) API 키 / 클라이언트
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
INDEX_NAME = st.secrets.get("PINECONE_INDEX", "ndtc-memory")
index = pc.Index(INDEX_NAME)


# =========================
# 4) 메뉴
# =========================
menu = st.sidebar.radio("업무 선택", ["AI 전략 비서 (Chat)", "지식 도서관 (자료 저장)", "대시보드"])


# =========================
# 5) 공통 유틸
# =========================
def category_label(opt: str) -> str:
    return f"{opt} — {CATEGORY_INFO.get(opt, '')}"


def safe_pdf_text(file_obj) -> str:
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
    try:
        d = docx.Document(file_obj)
        return "\n".join([p.text for p in d.paragraphs if p.text.strip()])
    except Exception:
        return ""


def txt_text(file_obj) -> str:
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
    resp = oai.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],
    )
    return resp.data[0].embedding


def upsert_text(*, text: str, category: str, filename: str, owner: str | None = None):
    """Pinecone에 텍스트 저장 (업무로그/개인로그/문서 모두 공용)"""
    vec = make_embedding(text)
    doc_id = str(uuid.uuid4())
    index.upsert(
        vectors=[
            {
                "id": doc_id,
                "values": vec,
                "metadata": {
                    "uploader": st.session_state.user_id,
                    "owner": owner,  # 개인로그는 owner에 user_id 저장
                    "filename": filename,
                    "category": category,
                    "text": text[:2000],
                    "created_at": int(time.time()),
                },
            }
        ]
    )
    return doc_id


def extract_text_from_upload(uploaded_file) -> str:
    """첨부 파일에서 텍스트 추출(문서/이미지)"""
    raw_text = ""
    ext = uploaded_file.name.split(".")[-1].lower()

    if ext == "pdf":
        raw_text = safe_pdf_text(uploaded_file)
        if not raw_text.strip():
            raw_text = "(PDF 텍스트 추출 실패: 스캔 PDF일 수 있습니다.)"

    elif ext == "docx":
        raw_text = docx_text(uploaded_file)

    elif ext == "txt":
        raw_text = txt_text(uploaded_file)

    elif ext in ["png", "jpg", "jpeg"]:
        raw_text = image_to_text(uploaded_file)

    return raw_text.strip()


# =========================
# 6) AI 전략 비서 (Chat)
# =========================
if menu == "AI 전략 비서 (Chat)":
    st.header("🤖 NDTC 수석 전략가 '엘투르'")

    # ✅ Claude 최신 모델 (Opus 4.6)
    # Anthropic Docs 기준: claude-opus-4-6  (Claude 3 Opus 은퇴 대체)
    CLAUDE_MODEL = st.secrets.get("CLAUDE_MODEL", "claude-opus-4-6")

    system_context = """
당신은 'NDTC(No Dealer Trading City Center)'의 수석 AI 전략가이자, 엘후스님의 개인 비서 '엘투르'입니다.

[역할]
- 개념을 쉽게 설명(교육자)
- 자료를 분석하고 적용점을 제안(분석가)
- 객관적 분별 제공(파트너)

[규칙]
- 내부 자료가 있으면 우선 근거로 사용
- 답변은 정중하고 논리적으로
"""

    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "엘투르입니다. 오늘은 어떤 전략을 논의할까요?"}]

    # ✅ 첨부(➕) 영역: 대화와 함께 파일/이미지 추가
    with st.expander("➕ 첨부 파일/이미지 추가 (질문과 함께 분석해서 반영)", expanded=False):
        chat_files = st.file_uploader(
            "여기에 파일/이미지를 추가하세요 (여러 개 가능)",
            type=["pdf", "txt", "docx", "png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key="chat_files",
        )
        st.caption("※ Streamlit 기본 채팅 입력창에는 내장 +버튼이 없어, 이 '첨부 영역'으로 동일 기능을 제공합니다.")

    # 대화 표시
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    prompt = st.chat_input("질문하거나 명령을 내려주세요...")

    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # 1) 첨부 텍스트 추출
        attachment_summary = ""
        if chat_files:
            chunks = []
            for f in chat_files:
                t = extract_text_from_upload(f)
                if t:
                    chunks.append(f"[첨부파일: {f.name}]\n{t[:2000]}")
            if chunks:
                attachment_summary = "\n\n".join(chunks)

        # 2) RAG 검색(전체 지식에서 top_k)
        knowledge_text = ""
        sources = []
        try:
            q_vec = make_embedding(prompt + ("\n" + attachment_summary if attachment_summary else ""))
            res = index.query(vector=q_vec, top_k=4, include_metadata=True)

            for match in res.get("matches", []):
                score = match.get("score", 0)
                meta = match.get("metadata", {}) or {}
                if score >= 0.70 and meta.get("text"):
                    sources.append(meta.get("filename", "unknown"))
                    knowledge_text += f"\n- ({meta.get('filename','unknown')}) {meta.get('text','')}"
        except Exception:
            pass

        # 3) 최종 프롬프트 구성
        final_prompt = f"""{prompt}

[첨부자료(사용자 제공)]
{attachment_summary if attachment_summary else "없음"}

[참고할 우리 팀 내부 자료]
{knowledge_text if knowledge_text.strip() else "관련된 내부 자료가 없습니다. 일반 지식으로 답변하세요."}
"""

        # 4) Claude 호출
        with st.chat_message("assistant"):
            try:
                resp = anthropic_client.messages.create(
                    model=CLAUDE_MODEL,
                    max_tokens=2000,
                    system=system_context,
                    messages=[{"role": "user", "content": final_prompt}],
                )
                answer = resp.content[0].text

                # 출처 표시
                if sources:
                    uniq = []
                    for s in sources:
                        if s not in uniq:
                            uniq.append(s)
                    answer += "\n\n---\n📚 참고한 내부 자료:\n" + "\n".join([f"- {x}" for x in uniq])

                st.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})

                # ✅ 저장 선택 UI (팀/개인 선택 후 저장)
                st.markdown("---")
                colA, colB = st.columns([2, 1])

                with colA:
                    save_target = st.selectbox(
                        "저장 위치 선택",
                        ["저장 안함", "대화 업무로그", "대화 개인로그"],
                        index=0,
                        key=f"save_target_{int(time.time())}",
                    )
                    st.caption("‘대화 개인로그’는 접속한 아이디별로 자동 분리 저장됩니다.")

                with colB:
                    if st.button("💾 지금 결과 저장", key=f"save_btn_{int(time.time())}"):
                        if save_target == "저장 안함":
                            st.warning("저장 위치를 선택해 주세요.")
                        else:
                            owner = st.session_state.user_id if save_target == "대화 개인로그" else None
                            upsert_text(
                                text=f"user: {prompt}\n\nassistant: {answer}",
                                category=save_target,
                                filename=f"{save_target}_{st.session_state.user_id}_{int(time.time())}.txt",
                                owner=owner,
                            )
                            st.success(f"✅ '{save_target}'로 저장했습니다.")

            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")


# =========================
# 7) 지식 도서관 (자료 저장)
# =========================
elif menu == "지식 도서관 (자료 저장)":
    st.header("📚 NDTC 지식 저장소")
    st.info("여러 파일을 한 번에 선택하고, 같은 카테고리로 일괄 저장할 수 있습니다.")

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

        for f in uploaded_files:
            with st.spinner(f"저장 중: {f.name}"):
                try:
                    raw_text = extract_text_from_upload(f)
                    if not raw_text:
                        fail_count += 1
                        st.warning(f"내용을 읽을 수 없어 저장하지 못했습니다: {f.name}")
                        continue

                    # 지식 도서관 저장은 owner 없음(공유)
                    upsert_text(
                        text=raw_text,
                        category=category,
                        filename=f.name,
                        owner=None,
                    )
                    ok_count += 1

                except Exception as e:
                    fail_count += 1
                    st.error(f"업로드 실패: {f.name} / {e}")

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
