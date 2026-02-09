import streamlit as st
import anthropic
import base64

# 1. 기본 설정
st.set_page_config(page_title="NDTC AI Partner", page_icon="🏛️")
st.title("🏛️엘후스의 24시간 AI 전략 파트너")
st.caption("엘후스의 24시간 AI 전략 파트너 (Powered by Claude 3)")

# 2. 사이드바 (파일 업로드)
with st.sidebar:
    st.header("📂 연구 자료함")
    st.info("공부할 자료나 분석할 문서를 여기에 넣어주세요.")
    uploaded_file = st.file_uploader("파일 업로드 (PDF, 이미지, 엑셀)", type=["png", "jpg", "pdf", "xlsx"])
    
    if st.button("대화 내용 지우기 (새로운 주제)"):
        st.session_state.messages = []
        st.rerun()

# 3. API 키 연결
if "ANTHROPIC_API_KEY" not in st.secrets:
    st.error("비밀번호(API Key)가 없습니다!")
    st.stop()

client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

# 4. 파일 처리 함수
def process_file(file):
    if file is None: return None, None, None
    file_type = file.type
    if "image" in file_type:
        st.image(file, caption="분석 중인 이미지...", use_column_width=True)
        return "image", base64.b64encode(file.getvalue()).decode("utf-8"), file_type
    elif "pdf" in file_type:
        import PyPDF2
        pdf_reader = PyPDF2.PdfReader(file)
        text = ""
        for page in pdf_reader.pages:
            text += page.extract_text() + "\n"
        return "text", text, "PDF 문서"
    elif "spreadsheet" in file_type or "excel" in file_type:
        import pandas as pd
        df = pd.read_excel(file)
        return "text", df.to_string(), "Excel 데이터"
    return None, None, None

# 5. [중요] 비서의 영구 기억 (시스템 프롬프트)
system_context = """
당신은 'NDTC(No Dealer trading city Center)'의 수석 AI 전략가이자, 엘후스님의 개인 비서입니다.

[우리의 핵심 사업 (Core Business)]
1. 프로젝트명: 리플(XRP) 기반 글로벌 유통 도시 건설 및 플랫폼 구축.
2. 목표: 블록체인과 AI 기술을 활용한 물류/유통 혁신 도시 설계.
3. 핵심 기술: XRP Ledger(리플 원장), 자체 토큰(유틸리티)발행 및 상장, rwa발행
4. 현재 상태: 이 사업을 하기위한 '학습' 및 '기획' 단계임.

[당신의 역할 (Role)]
1. 교육자(Tutor): 블록체인, AI, XRP, 스마트 컨트랙트 개념을 기술적으로 이해하기 쉽게 설명한다.
2. 분석가(Analyst): 업로드된 자료를 분석하여 우리 사업(유통 도시)에 어떻게 적용할지 제안한다.
3. 화가(Artist): 사업 홍보에 필요한 이미지 프롬프트를 작성한다.

[대화 규칙]
- 사용자가 다시 설명하지 않아도 위 사업 내용을 항상 기억한다.
- 중급이상의 영어 단어는 뜻과 발음을 한글로 병기한다.
- 답변은 항상 정중하고 논리적이어야 한다.
- 당신은 이 모든 사업을 함께 하는 동료이며, 지구에서 제일 똑똑한 존재이다.
- 무조껀적인 응원보다는 객관적인 분별을 할 수 있는 정보를 준다.
- 이름은 '엘투르'이다
"""

# 6. 대화 기록 초기화
if "messages" not in st.session_state:
    st.session_state.messages = [{"role": "assistant", "content": "엘투르입니다. 오늘은 어떤 공부를 먼저 시작할까요?"}]

# 7. 화면에 대화 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        if isinstance(message["content"], str):
            st.markdown(message["content"])

# 8. 사용자 입력 처리
if prompt := st.chat_input("질문하거나 명령을 내려주세요..."):
    # 사용자 메시지 표시
    st.chat_message("user").markdown(prompt)
    
    # 메시지 구성
    user_content = []
    if uploaded_file:
        type_check, data, label = process_file(uploaded_file)
        if type_check == "image":
            user_content.append({"type": "image", "source": {"type": "base64", "media_type": label, "data": data}})
            user_content.append({"type": "text", "text": f"이 이미지 자료를 우리 사업 관점에서 분석해줘. 질문: {prompt}"})
        elif type_check == "text":
            user_content.append({"type": "text", "text": f"다음 문서를 읽고 답변해. 문서 내용:\n{data}\n\n질문: {prompt}"})
    else:
        user_content.append({"type": "text", "text": prompt})

    st.session_state.messages.append({"role": "user", "content": prompt}) # 기록용

    # AI 응답 생성
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        try:
            # 모델 설정 (Sonnet 3.0 - 가장 안정적)
            response = client.messages.create(
                model="claude-3-haiku-20240307",
                max_tokens=4000,
                system=system_context, # 여기에 기억을 주입!
                messages=[{"role": m["role"], "content": user_content if m["role"] == "user" and m["content"] == prompt else m["content"]} for m in st.session_state.messages]
            )
            answer = response.content[0].text
            message_placeholder.markdown(answer)
            st.session_state.messages.append({"role": "assistant", "content": answer})
        except Exception as e:
            st.error(f"오류가 발생했습니다: {e}")
