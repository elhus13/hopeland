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
import PyPDF2  # PDF 처리를 위해 상단으로 이동

# =========================================================
# 1) 기본 설정
# =========================================================
st.set_page_config(page_title="NDTC Team HQ", page_icon="🏙️", layout="wide")

# =========================================================
# 2) 로그인(간단 인증)
# =========================================================
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
            # secrets가 없을 경우를 대비한 기본값 처리
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


# =========================================================
# 3) API 키 로드 & 클라이언트 연결
# =========================================================
st.sidebar.success(f"👤 접속자: {st.session_state.user_id}")
st.title("🏙️ NDTC 디지털 본부 (Hopeland)")
st.caption("AI & Blockchain 기반 무딜러 유통 혁신 플랫폼")

try:
    anthropic_key = st.secrets["ANTHROPIC_API_KEY"]
    pinecone_key = st.secrets["PINECONE_API_KEY"]
    openai_key = st.secrets["OPENAI_API_KEY"]
except Exception:
    st.error("⚠️ API 키 설정 오류: .streamlit/secrets.toml 파일에 ANTHROPIC / PINECONE / OPENAI 키가 있는지 확인하세요.")
    st.stop()

# Anthropic(Claude)
claude = anthropic.Anthropic(api_key=anthropic_key)

# OpenAI (SDK 안정형: 클라이언트 방식)
oai = OpenAI(api_key=openai_key)

# Pinecone
pc = Pinecone(api_key=pinecone_key)
INDEX_NAME = "ndtc-memory"
index = pc.Index(INDEX_NAME)


# =========================================================
# 4) 카테고리(한 칸에 설명 포함)
# =========================================================
CATEGORY_INFO = {
    "기술현황(Tech Scan)": "기술/툴/프로토콜 조사, 요약, 비교 자료",
    "시장/경쟁(Benchmark)": "경쟁사/유사 프로젝트, 사례 비교",
    "규제/정책(Regulation)": "법/정책/규정/리스크 분석",
    "공유회의(Sharing Meeting)": "중간 조사 공유, 브레인스토밍, 논의 기록(결정 전)",
    "결정회의(Decision Meeting)": "무엇을 하기로 했다가 명확한 확정 회의 기록",
    "설계/아키텍처(Architecture)": "구조도, 흐름, 데이터/결제/정산 설계 문서",
    "기획/문서(Planning Doc)": "제안서/피치덱/사업계획/로드맵 등 기획문서",
    "현장/증빙(Proof/Photos)": "사진/스캔/증빙/캡처 등 증거 자료",
    "대화 업무로그": "대화 결과/요약/결론을 팀 공용으로 저장",
    "대화 개인로그": "대화 결과/요약/메모를 접속자 ID별로 자동 분리 저장",
}
CATEGORIES = list(CATEGORY_INFO.keys())

def category_label(opt: str) -> str:
    return f"{opt} — {CATEGORY_INFO[opt]}"


# =========================================================
# 5) 공통 유틸: 텍스트 추출
# =========================================================
def extract_text_from_docx(uploaded_file) -> str:
    doc = docx.Document(uploaded_file)
    return "\n".join([p.text for p in doc.paragraphs])

def extract_text_from_txt(uploaded_file) -> str:
    return uploaded_file.read().decode("utf-8", errors="ignore")

def extract_text_from_pdf(uploaded_file) -> str:
    reader = PyPDF2.PdfReader(uploaded_file)
    out = []
    for page in reader.pages:
        out.append(page.extract_text() or "")
    return "\n".join(out)

def describe_image_with_openai(image_bytes: bytes) -> str:
    b64_img = base64.b64encode(image_bytes).decode("utf-8")
    resp = oai.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {
                "role": "user",
                "content": [
                    {"type": "text", "text": "이 이미지가 담고 있는 내용을 가능한 한 상세히 텍스트로 설명해줘."},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                ],
            }
        ],
    )
    return resp.choices[0].message.content

def make_embedding(text: str):
    # Pinecone/Embedding은 길이가 너무 길면 비용/시간이 커서 상한을 둡니다.
    text = (text or "").strip()
    if not text:
        return None
    resp = oai.embeddings.create(
        model="text-embedding-3-small",
        input=text[:8000],
    )
    return resp.data[0].embedding


# =========================================================
# 6) Pinecone 저장(카테고리/로그 구분)
# =========================================================
def upsert_to_pinecone(
    *,
    raw_text: str,
    filename: str,
    category: str,
    uploader: str,
    extra_meta: dict | None = None,
):
    vector = make_embedding(raw_text)
    if vector is None:
        raise ValueError("임베딩 생성 실패: 텍스트가 비어 있습니다.")

    doc_id = str(uuid.uuid4())

    # namespace 설계
    if category == "대화 개인로그":
        namespace = f"chat_personal_{uploader}"
    elif category == "대화 업무로그":
        namespace = "chat_team"
    else:
        namespace = "docs"

    metadata = {
        "uploader": uploader,
        "filename": filename,
        "category": category,
        "text": raw_text[:2000],  # Pinecone metadata 용량 고려
        "created_at": int(time.time()),
    }
    if extra_meta:
        metadata.update(extra_meta)

    # Pinecone 최신 SDK upsert 방식
    index.upsert(
        vectors=[(doc_id, vector, metadata)],
        namespace=namespace,
    )
    return doc_id, namespace


# =========================================================
# 7) 메뉴
# =========================================================
menu = st.sidebar.radio("업무 선택", ["AI 전략 비서 (Chat)", "지식 도서관 (자료 저장)", "대시보드"])


# =========================================================
# 8) AI 전략 비서 (Chat) + RAG + 결과 저장 + +첨부
# =========================================================
if menu == "AI 전략 비서 (Chat)":
    st.header("🤖 NDTC 수석 전략가 '엘투르'")

    # 시스템 프롬프트
    system_context = """
당신은 'NDTC(No Dealer trading city Center)'의 수석 AI 전략가이자, AI 동료 '엘투르'입니다.

[우리의 핵심 사업 (Core Business)]
1. 프로젝트명: 리플(XRP) 기반 글로벌 유통 도시 건설 및 플랫폼 구축.
2. 목표: 블록체인과 AI 기술을 활용한 물류/유통 혁신 도시 모델 설계, 유통센터 도시 건설
3. 핵심 기술: XRP Ledger(리플 원장), 자체 토큰(유틸리티)발행 및 상장, RWA 발행, 인공지능
4. 현재 상태: 이 사업을 하기 위한 '학습' 및 '기획' 단계임.

[당신의 역할 (Role)]
1. 교육자(Tutor): 기술 개념을 쉽게 설명한다.
2. 분석가(Analyst): 업로드된 자료를 분석하여 적용점을 제안한다.
3. 파트너(Partner): 무조건적 응원보다 객관적인 분별을 제공한다.

[대화 규칙]
- [참고자료]가 있다면 그것을 최우선으로 분석 근거로 삼는다.
- 영어 단어가 나올 경우 중급 이상의 영어 단어는 뜻과 발음을 한글로 병기한다.
"""

    # 세션 대화 기록
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "엘투르입니다. 오늘은 어떤 전략을 논의할까요?"}
        ]

    # “+ 첨부” 토글
    if "show_chat_uploader" not in st.session_state:
        st.session_state.show_chat_uploader = False

    # 최근 응답 저장용
    if "last_assistant_answer" not in st.session_state:
        st.session_state.last_assistant_answer = ""
    if "last_user_prompt" not in st.session_state:
        st.session_state.last_user_prompt = ""

    # 상단: 저장 UI
    st.divider()
    colA, colB = st.columns([3, 1])
    with colA:
        save_target = st.selectbox(
            "저장 위치 선택",
            ["저장 안함", "대화 업무로그", "대화 개인로그"],
            index=0,
            help="‘대화 개인로그’는 접속한 아이디별로 자동 분리 저장됩니다.",
        )
    with colB:
        save_now = st.button("💾 지금 결과 저장", use_container_width=True)

    if save_now:
        if save_target == "저장 안함":
            st.warning("저장 위치를 선택해 주세요.")
        else:
            try:
                content_to_save = st.session_state.last_assistant_answer.strip()
                if not content_to_save:
                    st.warning("저장할 결과가 없습니다. 먼저 질문을 보내고 답변을 받은 뒤 저장해 주세요.")
                else:
                    title = f"chat_{st.session_state.user_id}_{int(time.time())}.txt"
                    extra = {
                        "type": "chat_log",
                        "user_prompt": st.session_state.last_user_prompt[:2000],
                    }
                    upsert_to_pinecone(
                        raw_text=content_to_save,
                        filename=title,
                        category=save_target,
                        uploader=st.session_state.user_id,
                        extra_meta=extra,
                    )
                    st.success(f"✅ 저장 완료: {save_target}")
            except Exception as e:
                st.error(f"저장 실패: {e}")

    st.divider()

    # “+” 첨부 버튼(토글)
    col_plus, col_hint = st.columns([1, 6])
    with col_plus:
        if st.button("＋", help="파일/이미지 첨부 열기/닫기"):
            st.session_state.show_chat_uploader = not st.session_state.show_chat_uploader
    with col_hint:
        st.caption("‘＋’를 눌러 파일을 첨부한 뒤 질문을 보내면, 첨부 내용도 함께 반영됩니다.")

    chat_files = []
    if st.session_state.show_chat_uploader:
        chat_files = st.file_uploader(
            "첨부 파일 (여러 개 가능)",
            type=["pdf", "txt", "docx", "png", "jpg", "jpeg"],
            accept_multiple_files=True,
            key="chat_uploader_files",
        )

    # 대화 표시
    for m in st.session_state.messages:
        with st.chat_message(m["role"]):
            st.markdown(m["content"])

    # 입력창
    prompt = st.chat_input("Let's go")
    if prompt:
        st.session_state.last_user_prompt = prompt
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").markdown(prompt)

        # 1) RAG: Pinecone 검색
        knowledge_text = ""
        try:
            q_vec = make_embedding(prompt)
            if q_vec:
                search_res = index.query(
                    vector=q_vec,
                    top_k=3,
                    include_metadata=True,
                    namespace="docs",
                )
                found_docs = []
                for match in search_res.get("matches", []):
                    score = match.get("score", 0)
                    meta = match.get("metadata", {}) or {}
                    if score > 0.7:
                        found_docs.append(f"- {meta.get('filename','(unknown)')}: {meta.get('text','')}")
                if found_docs:
                    knowledge_text = "\n".join(found_docs)
        except Exception:
            pass

        # 2) 첨부 파일 텍스트 추출
        attachment_text_blocks = []
        if chat_files:
            for f in chat_files:
                try:
                    ext = f.name.split(".")[-1].lower()
                    if ext == "pdf":
                        t = extract_text_from_pdf(f)
                    elif ext == "docx":
                        t = extract_text_from_docx(f)
                    elif ext == "txt":
                        t = extract_text_from_txt(f)
                    else:
                        # image
                        img_bytes = f.getvalue()
                        t = describe_image_with_openai(img_bytes)
                    t = (t or "").strip()
                    if t:
                        attachment_text_blocks.append(f"[첨부: {f.name}]\n{t[:4000]}")
                except Exception as e:
                    attachment_text_blocks.append(f"[첨부: {f.name}] 처리 실패: {e}")

        attachment_text = "\n\n".join(attachment_text_blocks) if attachment_text_blocks else "첨부 없음"

        final_prompt = f"""
[사용자 질문]
{prompt}

[첨부 파일 내용 요약/추출]
{attachment_text}

[참고할 우리 팀 내부 자료(RAG)]
{knowledge_text if knowledge_text else "관련된 내부 자료가 없습니다. 일반 지식으로 답변하세요."}
"""

        # 3) Claude 호출
        with st.chat_message("assistant"):
            ph = st.empty()
            try:
                # Anthropic messages API
                # 참고: 2026년 기준 모델명은 실제 사용 가능한 모델로 조정 필요 (claude-3-5-sonnet 등)
                resp = claude.messages.create(
                    model="claude-3-5-sonnet-20240620", 
                    max_tokens=2000,
                    system=system_context,
                    messages=[
                        {"role": "user", "content": final_prompt}
                    ],
                )
                answer = resp.content[0].text

                # 참고 문서 표시
                if knowledge_text:
                    answer += "\n\n---\n📚 **참고한 내부 자료:**\n"
                    try:
                        for match in search_res.get("matches", []):
                            if match.get("score", 0) > 0.7:
                                meta = match.get("metadata", {}) or {}
                                answer += f"- {meta.get('filename','(unknown)')}\n"
                    except Exception:
                        pass

                ph.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
                st.session_state.last_assistant_answer = answer

            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")


# =========================================================
# 9) 지식 도서관 (자료 저장)
# =========================================================
elif menu == "지식 도서관 (자료 저장)":
    st.header("📚 NDTC 지식 저장소")
    st.info("여러 파일을 한 번에 선택해서 같은 카테고리로 일괄 저장할 수 있습니다.")

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
        st.caption(f"📌 선택된 분류 설명: {CATEGORY_INFO[category]}")

        saved = st.form_submit_button("💾 선택한 파일 모두 저장하기")

    if saved:
        if not uploaded_files:
            st.warning("파일을 선택해 주세요.")
            st.stop()

        ok_count, fail_count = 0, 0
        for f in uploaded_files:
            with st.spinner(f"저장 중: {f.name}"):
                try:
                    ext = f.name.split(".")[-1].lower()
                    raw_text = ""

                    if ext == "pdf":
                        raw_text = extract_text_from_pdf(f)
                    elif ext == "docx":
                        raw_text = extract_text_from_docx(f)
                    elif ext == "txt":
                        raw_text = extract_text_from_txt(f)
                    else:
                        # image
                        img_bytes = f.getvalue()
                        raw_text = describe_image_with_openai(img_bytes)
                        st.info(f"🖼️ 이미지 분석(앞부분): {raw_text[:120]}...")

                    raw_text = (raw_text or "").strip()
                    if not raw_text:
                        raise ValueError("파일에서 텍스트를 추출하지 못했습니다.")

                    upsert_to_pinecone(
                        raw_text=raw_text,
                        filename=f.name,
                        category=category,
                        uploader=st.session_state.user_id,
                        extra_meta={"type": "document"},
                    )

                    ok_count += 1
                except Exception as e:
                    fail_count += 1
                    st.error(f"❌ {f.name} 저장 실패: {e}")

        st.success(f"✅ 완료: 성공 {ok_count}개 / 실패 {fail_count}개")


# =========================================================
# 10) 대시보드
# =========================================================
elif menu == "대시보드":
    st.header("📊 NDTC 프로젝트 현황")
    st.write("팀원들과 공유할 공지사항이나 현황판입니다.")

    col1, col2, col3 = st.columns(3)
    col1.metric("현재 단계", "Phase 1", "기반 구축")
    col2.metric("지식 데이터", "Ready", "Pinecone 연동됨")
    col3.metric("팀원", "5명", "All Active")
