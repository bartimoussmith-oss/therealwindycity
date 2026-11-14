"""Owner-only, durable ZIP handoff for coding changes."""
import hmac

import streamlit as st

from tools.change_bundle import MAX_UPLOAD, inspect_bundle, publish_bundle

st.set_page_config(page_title="Change Bundle Upload", page_icon="📦", layout="wide")
st.title("📦 Change Bundle Upload")
st.write("Upload a ZIP of instructions, reference files, and proposed changes for the coding agent to review. Nothing inside the ZIP is executed or automatically applied to the site.")
st.warning("This repository is public. Saving a bundle publishes its entire contents to GitHub, including any hidden files. Do not upload passwords, API keys, personal records, or other confidential material.")

try:
    config = st.secrets.get("change_upload", {})
    password = str(config.get("password", ""))
    token = str(config.get("github_token", ""))
    branch = str(config.get("branch", ""))
except (FileNotFoundError, st.errors.StreamlitSecretNotFoundError):
    password = token = branch = ""

if not password or not token or not branch:
    st.info("Uploads are not configured yet. The site owner must add the change_upload password, github_token, and branch in Streamlit's server-side Secrets. See docs/CHANGE-BUNDLE-UPLOAD.md in the repository. No files are accepted or stored until setup is complete.")
    st.stop()

entered = st.text_input("Upload password", type="password")
if not entered or not hmac.compare_digest(entered.encode(), password.encode()):
    if entered:
        st.error("Incorrect upload password.")
    st.stop()

st.caption(f"Destination branch: {branch}. Limit: 15 MiB ZIP, 100 MiB expanded, 2,000 entries.")
st.write("For best results, include a README.md explaining what to change, priorities, and which files to use. PDFs, images, and source files can be included; scanning or OCR may still be needed during review.")
upload = st.file_uploader("Choose a change bundle", type=["zip"], accept_multiple_files=False)
if upload is not None:
    if upload.size > MAX_UPLOAD:
        st.error("ZIP exceeds 15 MiB. Split it into smaller bundles.")
        st.stop()
    data = upload.getvalue()
    try:
        # Cache only this session's last inspection, not archive bytes globally.
        import hashlib
        digest = hashlib.sha256(data).hexdigest()
        if st.session_state.get("bundle_digest") != digest:
            st.session_state["bundle_manifest"] = inspect_bundle(data)
            st.session_state["bundle_digest"] = digest
        manifest = st.session_state["bundle_manifest"]
    except ValueError as exc:
        st.error(str(exc))
        st.stop()
    st.success(f"Validated {len(manifest['files'])} files; {manifest['expanded_bytes']:,} expanded bytes.")
    st.dataframe(manifest["files"], hide_index=True, use_container_width=True)
    st.code(manifest["sha256"], language=None)
    confirmed = st.checkbox("I reviewed the contents and approve publishing this ZIP to the public GitHub repository.", key=f"approve_{digest}")
    if st.button("Save bundle to GitHub", disabled=not confirmed):
        try:
            with st.spinner("Saving bundle to GitHub…"):
                receipt = publish_bundle(data, digest, token, branch)
            st.session_state["bundle_receipt"] = receipt
        except ValueError as exc:
            st.error(str(exc))

receipt = st.session_state.get("bundle_receipt")
if receipt:
    st.success("Bundle saved durably to GitHub. It survives site restarts.")
    st.link_button("View saved ZIP on GitHub", receipt["url"])
    st.write("Copy this handoff into your Arena conversation so the agent can retrieve it. Uploading does not automatically notify or start an agent.")
    st.code(f"Please review the change bundle at {receipt['path']}\nCommit: {receipt['commit']}\nRepository: bartimoussmith-oss/therealwindycity", language=None)
