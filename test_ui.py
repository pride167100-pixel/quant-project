import streamlit as st

st.title("퀀트 스크리너 - 테스트 화면")

st.write("이 화면이 보이면 Streamlit이 정상 작동하는 겁니다!")

value = st.slider("PBR 이하", 0.1, 3.0, 1.0, 0.1)
st.write("선택한 PBR 값:", value)