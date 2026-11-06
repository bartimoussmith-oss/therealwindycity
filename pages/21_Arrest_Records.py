import streamlit as st

st.title("Arrest directory layout demonstration")
st.error("FICTIONAL DEMONSTRATION ONLY. The two examples below are fabricated Python literals, not public records, real arrests, legal citations, or detention statuses. Do not cite or use them as evidence.")
st.caption("This page does not connect to a live arrest system, decryption tunnel, or verification service. For the separate source-backed database, use the Arrest Database page; its access and source limitations still apply.")

# Historical synthetic examples retained only for transparent demo provenance.
examples = [
    {"date": "2026-10-18", "id": "ARR-7819", "charges": "Interference with Public Safety Radio Systems (18-19.1)", "status": "PROCESSED"},
    {"date": "2026-10-19", "id": "ARR-7820", "charges": "Unlawful Access inside Secured Communications Loop", "status": "PENDING DETENTION"},
]

with st.expander("Show fictional layout examples (not evidence)", expanded=False):
    for example in examples:
        st.subheader("FICTIONAL EXAMPLE: " + example["id"])
        st.write({"synthetic_example": True, **example})
    st.warning("All dates, references, charge text, and statuses above are fictional demo content.")
