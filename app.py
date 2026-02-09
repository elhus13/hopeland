import streamlit as st
import anthropic
import pandas as pd
import PyPDF2
import base64
from io import BytesIO

# 1. 기본 설정 (Settings [세팅스])
st.set_page_config(page_title="NDTC AI Secretary", page_icon="🤖")
st.title("🤖 엘후스님의 멀티모달 비서")
st.caption("Eyes & Ears & Brain (Powered by Claude)")

# 2. 사이드바 - 파일 업로드 기능 (Upload [업로드])
with st.sidebar:
    st.header("📂 자료 입력 (Input [인풋])")
    uploaded_file = st.file_uploader("이미지, PDF, 엑셀을 올려주세요", type=["png", "jpg", "jpeg", "pdf", "xlsx"])
    
    if st.button("대화 내용 지우기 (Clear [클리어])"):
        st.session_state.messages = []
        st.rerun()

# 3. API 키 확인
if "ANTHROPIC_API_KEY" not in st.secrets:
    st.error("비밀번호(API Key)가 없습니다! Secrets를 확인해주세요.")
    st.stop()

client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

# 4. 파일 처리 함수 (Processing [프로세싱])
def process_file(file):
    file_type = file.type
    
    # A. 이미지일 경우
    if "image" in file_type:
        st.image(file, caption="업로드된 이미지", use_column_width=True)
        # 이미지를 base64로 변환 (AI가 볼 수 있게)
        encoded_string = base64.b64encode(file.getvalue()).decode("utf-8")
        return "image", encoded_string, file_type
        
    # B. PDF일 경우
    elif "pdf" in file_type:
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return "text", text, "PDF 문서"
        
    # C. 엑셀일 경우
    elif "spreadsheet" in file_type or "excel" in file_type:
        df = pd.read_excel(file)
        text = df.to_string() # 엑셀을 텍스트로 변환
        return "text", text, "Excel 데이터"
    
    return None, None, None

# 5. 대화 기록 초기화
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "안녕하세요! 문서나 이미지를 주시면 제가 분석해 드리겠습니다. (Analysis [어낼러시스])"}
    ]

# 6. 이전 대화 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        # 이미지가 있는 메시지는 텍스트만 보여줌 (간략화)
        if isinstance(message["content"], list):
            for block in message["content"]:
                if block["type"] == "text":
                    st.markdown(block["text"])
        else:
            st.markdown(message["content"])

# 7. 채팅 입력 및 응답 로직
if prompt := st.chat_input("명령을 내려주세요..."):
    
    # 사용자 메시지 구조 만들기
    user_message_content = []
    
    # 7-1. 파일이 있으면 먼저 처리
    if uploaded_file:
        type_check, data, label = process_file(uploaded_file)
        
        if type_check == "image":
            # 이미지 데이터 추가
            user_message_content.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": label,
                    "data": data,
                },
            })
            user_message_content.append({"type": "text", "text": f"이 이미지와 함께 질문합니다: {prompt}"})
            st.toast("이미지를 보고 있습니다... (Viewing [뷰잉])")
            
        elif type_check == "text":
            # 문서 데이터 추가
            context = f"다음은 업로드된 {label}의 내용입니다:\n\n{data}\n\n사용자 질문: {prompt}"
            user_message_content.append({"type": "text", "text": context})
            st.toast("문서를 읽고 있습니다... (Reading [리딩])")
    else:
        # 파일 없으면 그냥 텍스트만
        user_message_content.append({"type": "text", "text": prompt})

    # 7-2. 화면에 표시 (Display [디스플레이])
    st.session_state.messages.append({"role": "user", "content": user_message_content})
    with st.chat_message("user"):
        st.markdown(prompt)
        if uploaded_file:
            st.caption(f"📎 첨부파일: {uploaded_file.name}")

    # 7-3. 비서 응답 생성
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        try:
            response = client.messages.create(
                model="claude-3-haiku-20240307", 
                max_tokens=2000,
                # 영어 공부 시스템 프롬프트 유지!
                system="너는 NDTC의 수석 AI 전략가입니다. 이미지 분석, 데이터 요약, 영어 교육을 담당합니다. 답변할 때 중요한 영어 단어가 나오면 반드시 뒤에 [한글 발음]을 괄호 안에 적어주세요.",
                messages=st.session_state.messages
            )
            
            answer = response.content[0].text
            message_placeholder.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
            
        except Exception as e:
            st.error(f"오류가 발생했습니다 (Error [에러]): {e}")
