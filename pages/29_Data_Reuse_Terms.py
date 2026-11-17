from pathlib import Path
import streamlit as st

st.set_page_config(page_title='Data Reuse Terms', layout='wide')
st.title('Data Reuse Terms')
notice = Path(__file__).resolve().parents[1] / 'DATA-LICENSE.md'
if notice.is_file():
    text = notice.read_text(encoding='utf-8')
    st.markdown(text)
    st.download_button('Download data reuse notice', text, file_name='DATA-LICENSE.md', mime='text/markdown')
else:
    st.error('The data reuse notice is unavailable in this deployed revision. No replacement terms are inferred.')
