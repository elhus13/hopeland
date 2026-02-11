import uuid
import streamlit as st
import anthropic
import openai
from pinecone import Pinecone
import time
import base64
import docx # 워드 파일용
import io
from PIL import Image # 이미지 처리용

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
        
        submitted = st.form_submit_button("출근하기")
        
        if submitted:
            # Secrets에서 비밀번호 가져오기 (없으면 기본값)
            valid_users = st.secrets.get("passwords", {"admin": "1234", "team": "ndtc2026"})
            
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
# [메인] 시스템 초기화
# ==========================================
st.sidebar.success(f"👤 접속자: {st.session_state.user_id}")
st.title("🏙️ NDTC 디지털 본부 (Hopeland)")
st.caption("AI & Blockchain 기반 무딜러 유통 혁신 플랫폼")

# API 키 로드
try:
    anthropic_key = st.secrets["ANTHROPIC_API_KEY"]
    pinecone_key = st.secrets["PINECONE_API_KEY"] # DB용
    openai_key = st.secrets["OPENAI_API_KEY"] # 임베딩 및 비전용
except:
    st.error("⚠️ API 키 설정 오류: Secrets에 키가 있는지 확인하세요.")
    st.stop()

# 클라이언트 연결
client = anthropic.Anthropic(api_key=anthropic_key)
openai.api_key = openai_key
pc = Pinecone(api_key=pinecone_key)
index = pc.Index("ndtc-memory") # 우리가 만든 인덱스 이름

# 메뉴 구성
menu = st.sidebar.radio("업무 선택", ["AI 전략 비서 (Chat)", "지식 도서관 (자료 저장)", "대시보드"])

# ------------------------------------------
# 1. AI 전략 비서 (엘투르) - RAG 적용
# ------------------------------------------
if menu == "AI 전략 비서 (Chat)":
    st.header("🤖 NDTC 수석 전략가 '엘투르'")
    
    # 엘후스님의 기존 프롬프트 유지
    system_context = """
    당신은 'NDTC(No Dealer trading city Center)'의 수석 AI 전략가이자, 엘후스님의 개인 비서 '엘투르'입니다.

    [우리의 핵심 사업 (Core Business)]
    1. 프로젝트명: 리플(XRP) 기반 글로벌 유통 도시 건설 및 플랫폼 구축.
    2. 목표: 블록체인과 AI 기술을 활용한 물류/유통 혁신 도시 설계.
    3. 핵심 기술: XRP Ledger(리플 원장), 자체 토큰(유틸리티)발행 및 상장, RWA 발행
    4. 현재 상태: 이 사업을 하기 위한 '학습' 및 '기획' 단계임.

    [당신의 역할 (Role)]
    1. 교육자(Tutor): 기술 개념을 쉽게 설명한다.
    2. 분석가(Analyst): 업로드된 자료를 분석하여 적용점을 제안한다.
    3. 파트너(Partner): 무조건적 응원보다 객관적인 분별을 제공한다.

    [대화 규칙]
    - [참고자료]가 있다면 그것을 최우선으로 분석 근거로 삼는다.
    - 중급 이상의 영어 단어는 뜻과 발음을 한글로 병기한다.
    - 답변은 항상 정중하고 논리적이어야 한다.
    """

    # 대화 기록 초기화
    if "messages" not in st.session_state:
        st.session_state.messages = [{"role": "assistant", "content": "엘투르입니다. 오늘은 어떤 전략을 논의할까요?"}]

    # 대화 내용 표시
    for message in st.session_state.messages:
        with st.chat_message(message["role"]):
            st.markdown(message["content"])

    # 입력 처리
    if prompt := st.chat_input("질문하거나 명령을 내려주세요..."):
        st.session_state.messages.append({"role": "user", "content": prompt})
        st.chat_message("user").markdown(prompt)

        # 1) 지식 도서관 검색 (RAG)
        knowledge_text = ""
        try:
            # 질문을 숫자로 변환 (Embedding)
            q_resp = openai.embeddings.create(input=prompt, model="text-embedding-3-small")
            q_vector = q_resp.data[0].embedding
            
            # Pinecone에서 관련 문서 검색
            search_res = index.query(vector=q_vector, top_k=3, include_metadata=True)
            
            # 검색된 내용 정리
            found_docs = []
            for match in search_res['matches']:
                if match['score'] > 0.7: # 유사도가 70% 이상인 것만 참고
                    found_docs.append(f"- {match['metadata']['filename']}: {match['metadata']['text']}")
            
            if found_docs:
                knowledge_text = "\n".join(found_docs)
                
        except Exception as e:
            # 검색 실패해도 대화는 이어가도록 함
            pass

        # 2) 엘투르에게 질문 전달 (지식 포함)
        final_prompt = f"""
        {prompt}
        
        [참고할 우리 팀 내부 자료]
        {knowledge_text if knowledge_text else "관련된 내부 자료가 없습니다. 일반 지식으로 답변하세요."}
        """

        # AI 응답 생성
        with st.chat_message("assistant"):
            message_placeholder = st.empty()
            try:
                response = client.messages.create(
                    model="claude-3-haiku-20240307",
                    max_tokens=4000,
                    system=system_context,
                    messages=[{"role": m["role"], "content": final_prompt if m["role"] == "user" and m["content"] == prompt else m["content"]} for m in st.session_state.messages]
                )
                answer = response.content[0].text
                
                # 출처 표시
                if knowledge_text:
                    answer += "\n\n---\n📚 **참고한 내부 자료:**\n" + "\n".join([f"- {m['metadata']['filename']}" for m in search_res['matches'] if m['score'] > 0.7])
                
                message_placeholder.markdown(answer)
                st.session_state.messages.append({"role": "assistant", "content": answer})
                
            except Exception as e:
                st.error(f"오류가 발생했습니다: {e}")

# ------------------------------------------
# 2. 지식 도서관 (자료 업로드)
# ------------------------------------------
elif menu == "지식 도서관 (자료 저장)":
    st.header("📚 NDTC 지식 저장소")
    st.info("팀원들이 가진 PDF, 워드, 텍스트, 이미지 파일을 여기에 업로드하세요.")
    
    with st.form("upload_form"):
        # [기능 추가] docx, png, jpg 지원
        uploaded_file = st.file_uploader("파일 선택", type=["pdf", "txt", "docx", "png", "jpg", "jpeg"])
        category = st.selectbox("자료 분류", ["시장조사", "기술문서", "기획안", "회의록", "현장사진"])
        saved = st.form_submit_button("💾 도서관에 저장하기")
        
        if saved and uploaded_file:
            with st.spinner("자료를 분석하여 저장 중입니다..."):
                try:
                    # 텍스트 추출 로직
                    raw_text = ""
                    file_ext = uploaded_file.name.split('.')[-1].lower()
                    
                    # [A] 문서 파일 처리
                    if file_ext == "pdf":
                        import PyPDF2
                        reader = PyPDF2.PdfReader(uploaded_file)
                        for page in reader.pages:
                            raw_text += page.extract_text()
                    
                    elif file_ext == "docx":
                        doc = docx.Document(uploaded_file)
                        raw_text = "\n".join([p.text for p in doc.paragraphs])
                    
                    elif file_ext == "txt":
                        raw_text = uploaded_file.read().decode("utf-8")

                    # [B] 이미지 파일 처리 (GPT-4o Vision)
                    elif file_ext in ["png", "jpg", "jpeg"]:
                         # 이미지를 base64로 변환
                        img_bytes = uploaded_file.getvalue()
                        b64_img = base64.b64encode(img_bytes).decode('utf-8')
                        
                        # OpenAI Vision에게 설명 요청
                        vision_resp = openai.chat.completions.create(
                            model="gpt-4o-mini",
                            messages=[
                                {
                                    "role": "user",
                                    "content": [
                                        {"type": "text", "text": "이 이미지가 담고 있는 내용을 상세히 텍스트로 설명해줘."},
                                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64_img}"}}
                                    ]
                                }
                            ]
                        )
                        raw_text = vision_resp.choices[0].message.content
                        st.info(f"🖼️ 이미지 분석 내용: {raw_text[:100]}...")
                    
                    # 3) 임베딩 & 저장 (공통)
                    if raw_text:
                       emb_resp = openai.embeddings.create(
                           input=raw_text[:8000],
                           model="text-embedding-3-small"
                       )
                      vector = emb_resp.data[0].embedding

                      doc_id = str(uuid.uuid4())  # 🟩 핵심: 한글 파일명 대신 안전한 ID 사용

                      index.upsert([
                         (doc_id, vector, {
                           "uploader": st.session_state.user_id,
                           "filename": uploaded_file.name,   # 파일명은 metadata에 보관
                           "category": category,
                           "text": raw_text[:2000]
                       })
                   ])

                   st.success("✅ 저장 완료! 이제 엘투르가 이 내용을 기억합니다.")
             else:
               st.warning("파일에서 내용을 읽을 수 없습니다.")
  
                        
                except Exception as e:
                    st.error(f"업로드 실패: {e}")

# ------------------------------------------
# 3. 대시보드
# ------------------------------------------
elif menu == "대시보드":
    st.header("📊 NDTC 프로젝트 현황")
    st.write("팀원들과 공유할 공지사항이나 현황판입니다.")
    
    col1, col2, col3 = st.columns(3)
    col1.metric("현재 단계", "Phase 1", "기반 구축")
    col2.metric("지식 데이터", "Ready", "Pinecone 연동됨")
    col3.metric("팀원", "5명", "All Active")
