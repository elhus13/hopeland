import streamlit as st
import anthropic

# 1. 기본 설정
st.set_page_config(page_title="NDTC AI Secretary", page_icon="🤖")
st.title("🤖 엘후스님의 AI 비서 (Powered by Claude)")

# 2. 사이드바 (옵션)
with st.sidebar:
    st.header("설정")
    st.write("NDTC Central Control")
    if st.button("대화 내용 지우기"):
        st.session_state.messages = []
        st.rerun()

# 3. API 키 확인 (금고에서 꺼내기)
if "ANTHROPIC_API_KEY" not in st.secrets:
    st.error("비밀번호(API Key)가 설정되지 않았습니다! Secrets를 확인해주세요.")
    st.stop()

# 클라이언트 생성
client = anthropic.Anthropic(api_key=st.secrets["ANTHROPIC_API_KEY"])

# 4. 대화 기록 초기화
if "messages" not in st.session_state:
    st.session_state.messages = [
        {"role": "assistant", "content": "안녕하세요, 엘후스님! 무엇을 도와드릴까요?"}
    ]

# 5. 이전 대화 화면에 표시
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# 6. 채팅 입력 및 응답 로직
if prompt := st.chat_input("메시지를 입력하세요..."):
    # 유저 메시지 표시
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)

    # 비서 응답 생성
    with st.chat_message("assistant"):
        message_placeholder = st.empty()
        
        try:
            # Claude에게 질문 던지기
            response = client.messages.create(
                model="claude-3-haiku-20240307", # 가장 가벼운 모델
                max_tokens=1000,
                messages=[
                    {"role": m["role"], "content": m["content"]}
                    for m in st.session_state.messages
                ]
            )
            
            # 응답 받아서 표시
            answer = response.content[0].text
            message_placeholder.markdown(answer)
            
            # 대화 기록에 저장
            st.session_state.messages.append({"role": "assistant", "content": answer})
            
        except Exception as e:
            st.error(f"에러가 발생했습니다: {e}")
