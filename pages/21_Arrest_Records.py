import streamlit as st

st.markdown(
    """
    <style>
    .reportview-container, .main {
        background-color: #0B0C10;
        color: #00FF66;
        font-family: 'Courier New', monospace;
    }
    .terminal-card {
        background-color: #1F2833;
        border: 1px solid #45A29E;
        border-left: 6px solid #66FCF1;
        padding: 15px;
        border-radius: 4px;
        margin-bottom: 12px;
    }
    .header-bar {
        border-bottom: 2px solid #FF3366;
        padding-bottom: 8px;
        margin-bottom: 15px;
    }
    </style>
    """,
    unsafe_allow_html=True
)

st.markdown("<div class='header-bar'><h1>PROMETHEAN V-MAX // ARREST PATH DIRECTORY</h1></div>", unsafe_allow_html=True)
st.write("System Status: ONLINE | Active Decryption Tunnel Ready")

arrests = [
    {"date": "2026-10-18", "id": "ARR-7819", "charges": "Interference with Public Safety Radio Systems (18-19.1)", "status": "PROCESSED"},
    {"date": "2026-10-19", "id": "ARR-7820", "charges": "Unlawful Access inside Secured Communications Loop", "status": "PENDING DETENTION"}
]

for record in arrests:
    st.markdown(f"""
    <div class='terminal-card'>
        <span style='color:#FF3366; font-weight:bold;'>[ALERT // {record['date']}]</span><br/>
        <strong>RECORD REF:</strong> {record['id']}<br/>
        <strong>OFFENSE LOG:</strong> {record['charges']}<br/>
        <strong>DISPOSITION:</strong> <span style='color:#66FCF1;'>{record['status']}</span>
    </div>
    """, unsafe_allow_html=True)
