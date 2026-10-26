"""Embed the separately hosted full application; never start a local Node process."""
import ipaddress
import os
from urllib.parse import urlsplit

import streamlit as st
import streamlit.components.v1 as components

st.set_page_config(page_title="God's Eye View | The Real Windy City", page_icon="🌐", layout="wide")
st.title("God's Eye View")
st.caption("Independent full-application workspace. Existing civic pages and source records are unchanged.")


def valid_app_url(raw):
    try:
        if not raw or any(ch.isspace() or ord(ch) < 32 for ch in raw):
            return False
        u = urlsplit(raw)
        host = (u.hostname or "").lower().rstrip(".")
        if u.scheme != "https" or not host or u.username or u.password or u.query or u.fragment or u.port not in (None, 443):
            return False
        if host == "localhost" or host.endswith((".localhost", ".local", ".internal")) or "." not in host:
            return False
        try:
            if not ipaddress.ip_address(host).is_global:
                return False
        except ValueError:
            pass
        return True
    except ValueError:
        return False


url = os.environ.get("GODS_EYE_APP_URL", "").strip()
if not url:
    try:
        url = str(st.secrets.get("GODS_EYE_APP_URL", "")).strip()
    except Exception:
        url = ""

st.markdown("The embedded application runs on a separate service. Its data-provider terms, availability and permissions still apply. This page does not copy civic records into that service.")
if not url:
    st.warning("The full God’s Eye application endpoint has not been configured. No globe or live feed is being loaded.")
    st.info("Owner setup: deploy the full upstream Node/Docker application, then set GODS_EYE_APP_URL in this Streamlit app’s secrets or server environment to its public HTTPS root URL. Never put API keys in that URL or in GitHub.")
    st.markdown("[Upstream application](https://github.com/bilawalsidhu/gods-eye-view)")
    st.stop()

if not valid_app_url(url):
    st.error("Invalid GODS_EYE_APP_URL. Use a public HTTPS URL on port 443, without credentials, query parameters or fragments. Configuration has not been displayed.")
    st.stop()

st.link_button("Open full application in a separate tab", url)
st.caption("Opening or embedding contacts the external host and its providers. Microphone, fullscreen, login and some browser features may require the separate-tab view. A configured URL is not proof that the app or any particular feed is healthy.")
height = st.slider("Workspace height", min_value=500, max_value=1400, value=900, step=50)
load = st.checkbox("Load the external full application in this page", value=False)
if load:
    components.iframe(url, height=height, scrolling=True)
    st.caption("If the frame is blank or blocked, use the separate-tab button. The host must allow framing by this Streamlit deployment; this page does not bypass CSP, X-Frame-Options or authentication.")
else:
    st.info("External application not loaded. Enable the checkbox when ready.")
