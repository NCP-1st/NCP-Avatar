# 실행: cd frontend && streamlit run app.py
import streamlit as st

st.set_page_config(page_title="Mediary", page_icon="📔", layout="wide")

pages = [
    st.Page("pages/diary.py", title="일기 채팅", icon="📔", default=True),
    st.Page("pages/counsel.py", title="나만의 상담사", icon="💬"),
    st.Page("pages/calendar.py", title="캘린더 조회", icon="📅"),
    st.Page("pages/map.py", title="지도 조회", icon="🗺️"),
]

st.navigation(pages).run()
