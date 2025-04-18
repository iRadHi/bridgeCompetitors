import streamlit as st

# Only set_page_config in the main file
st.set_page_config(
    page_title="Bridge Results Dashboard",
    layout="wide",
    page_icon="♠️"
)

st.title("♠️ Bridge Results Dashboard")
st.markdown("""
    Welcome to the bridge results tracker. Select a section:
    
    - **NBO Results**: Competition results from bridge.co.il
    - **BBO Results**: Hand records from BridgeBase Online (coming soon)
""")

col1, col2 = st.columns(2)
with col1:
    st.page_link("pages/1_NBO.py", label="🇮🇱 Go to NBO Results", icon="📊")
with col2:
    st.page_link("pages/2_BBO.py", label="♠️ Go to BBO Results", icon="🔍")

st.markdown("---")
st.caption("Note: The BBO section is currently under development")