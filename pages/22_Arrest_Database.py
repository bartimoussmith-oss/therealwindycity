"""Password gate in front of the de-identified arrest database.

WHY THIS PAGE EXISTS
    The rest of this app is open. This page is the one that serves the arrest
    database, so it is the one that carries a gate. It reuses the viewer in
    tools/arrest_explorer.py rather than duplicating it -- there is one copy of
    the rendering logic and one copy of the data rules.

WHERE THE PASSWORD LIVES
    In Streamlit secrets only (`.streamlit/secrets.toml` locally, or the
    "Secrets" panel of the app's settings on Streamlit Community Cloud):

        arrest_page_password = "CHANGE-ME-see-note-below"
        # ^ placeholder. Do NOT use this value -- it is committed to a public
        #   repository, so anyone can read it. The page refuses it at runtime.

    It is NEVER in this repository, never in a commit, and never printed. If the
    secret is absent this page fails closed: it shows no data at all and tells
    the owner how to set it. `ARREST_PAGE_PASSWORD` in the environment is
    honoured as a fallback so the page can be exercised on a local machine
    without writing a secrets file; Streamlit Cloud only offers secrets, so that
    path is for development.

WHAT THE GATE DOES AND DOES NOT DO
    It is an access gate on a de-identified dataset, not secrecy about the
    arrests themselves -- those were published by a news outlet and are public
    record. Names and exact ages are not in the data this page serves at all:
    tools/import_master_arrest_db.py strips them and audits the result before it
    is written, and the sealed keyring is gitignored and never committed. So a
    leaked password here exposes nothing identifying. That is deliberate.
"""
from __future__ import annotations

import hmac
import os
import runpy
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parent.parent
EXPLORER = ROOT / "tools" / "arrest_explorer.py"
ARREST_DIR = ROOT / "data" / "arrests"

# Files this page is allowed to serve. Everything else in data/arrests/ is sealed.
PUBLIC_FILES = ("master_records.json", "records.json")
SEALED_FILES = ("keyring.jsonl", "name_key.json", "access_ledger.json")

MAX_ATTEMPTS = 8

st.set_page_config(page_title="Arrest Database — access gated", page_icon="🔒", layout="wide")


def configured_password() -> str | None:
    """Read the gate password from Streamlit secrets, else the environment."""
    for key in ("arrest_page_password", "ARREST_PAGE_PASSWORD"):
        try:
            val = st.secrets.get(key)
        except Exception:
            val = None
        if isinstance(val, str) and val:
            return val
    env = os.environ.get("ARREST_PAGE_PASSWORD")
    return env if env else None


# A password that appears in this public repository protects nothing.
# Compared case-insensitively, so every entry here MUST be lowercase.
PUBLIC_PLACEHOLDERS = frozenset({
    "change-me-see-note-below",   # the example in this file's own docs
    "changeme", "password", "passwordpassword", "arrest", "arrestrecords",
    "cheyenne", "therealwindycity",
})
MIN_PASSWORD_LENGTH = 12


def not_configured() -> None:
    st.error("🔒 **This page is closed: no access password is configured.**")
    st.markdown(
        """
No arrest data is being served. Nothing is exposed -- the page fails closed.

To open it, set the password as a **Streamlit secret**. Never commit it.

**On Streamlit Community Cloud**
1. App dashboard → your app → ⚙️ **Settings** → **Secrets**
2. Add:
   ```toml
   arrest_page_password = "CHANGE-ME-see-note-below"
   ```
   ⚠️ That value is a placeholder, not a password. It is committed to this
   public repository, so **this page refuses to run with it**. Use a passphrase
   of your own — several unrelated words, at least 12 characters.
3. **Save**, then let the app restart.

**Locally** — create `.streamlit/secrets.toml` (already gitignored) with the same
line, or export `ARREST_PAGE_PASSWORD` in the shell you launch Streamlit from.

Use a passphrase rather than a short word: this gate is only as strong as the
password, and it can be tried repeatedly by anyone who finds the page.
"""
    )
    st.stop()


def lock_panel() -> None:
    st.markdown("## 🔒 Arrest database — password required")
    st.caption(
        "De-identified arrest records. Names published: **0**. Exact ages published: **0**. "
        "Released only for public-safety and non-discriminatory research purposes."
    )
    attempts = st.session_state.get("arrest_attempts", 0)
    if attempts >= MAX_ATTEMPTS:
        st.error(
            f"Too many incorrect attempts ({attempts}). Reload the page to try again. "
            "If you are the owner, the password is in your Streamlit secrets."
        )
        st.stop()

    with st.form("arrest_gate"):
        pw = st.text_input("Access password", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Open the database", width="stretch")

    if submitted:
        expected = st.session_state.get("_arrest_expected") or ""
        # Constant-time compare, and never echo what was typed.
        if pw and hmac.compare_digest(pw.encode("utf-8"), expected.encode("utf-8")):
            st.session_state.arrest_unlocked = True
            st.session_state.arrest_attempts = 0
            st.rerun()
        st.session_state.arrest_attempts = attempts + 1
        remaining = MAX_ATTEMPTS - st.session_state.arrest_attempts
        st.error(
            "Incorrect password."
            + (f" {remaining} attempt{'s' if remaining != 1 else ''} before this page locks."
               if remaining > 0 else "")
        )


def serve() -> None:
    """Render the real viewer, sharing one copy of the logic."""
    top = st.container()
    with top:
        cols = st.columns([6, 1])
        cols[0].caption(
            "🔓 Unlocked. Serving the public, de-identified tier from `data/arrests/`."
        )
        if cols[1].button("Lock", width="stretch"):
            st.session_state.arrest_unlocked = False
            st.rerun()

    missing = [f for f in PUBLIC_FILES if not (ARREST_DIR / f).exists()]
    if missing and len(missing) == len(PUBLIC_FILES):
        st.warning(
            "No public arrest data found in `data/arrests/`. "
            "Run `tools/import_master_arrest_db.py` (or `tools/build_arrest_records.py`) first."
        )
        return

    if not EXPLORER.exists():
        st.error(f"Viewer is missing: `{EXPLORER.relative_to(ROOT)}`")
        return

    # The viewer owns set_page_config when run standalone; suppress that here so
    # Streamlit does not raise on a second call.
    os.environ["ARREST_EXPLORER_EMBEDDED"] = "1"
    try:
        runpy.run_path(str(EXPLORER), run_name="__embedded_arrest_page__")
    finally:
        os.environ.pop("ARREST_EXPLORER_EMBEDDED", None)


# ------------------------------------------------------------------ run

expected = configured_password()
if not expected:
    not_configured()          # calls st.stop()

if expected.strip().lower() in PUBLIC_PLACEHOLDERS:
    st.error(
        "🔒 **This page is closed: the configured password is the placeholder from this "
        "repository's own documentation.** It is committed to a public repo, so it protects "
        "nothing. Set a real passphrase in your Streamlit secrets."
    )
    st.stop()

if len(expected) < MIN_PASSWORD_LENGTH:
    st.error(
        f"🔒 **This page is closed: the configured password is {len(expected)} characters.** "
        f"Minimum is {MIN_PASSWORD_LENGTH}. This gate can be tried repeatedly by anyone who "
        "finds the page, so a short password is not adequate. Use a passphrase."
    )
    st.stop()

st.session_state.setdefault("arrest_unlocked", False)
st.session_state["_arrest_expected"] = expected

present = [f for f in PUBLIC_FILES if (ARREST_DIR / f).exists()]
sealed_here = [f for f in SEALED_FILES if (ARREST_DIR / f).exists()]

if not st.session_state.arrest_unlocked:
    lock_panel()
    with st.expander("What this gate protects, and what it does not"):
        st.markdown(
            f"""
**Served once unlocked** — {", ".join(f"`{f}`" for f in present) or "nothing (no data found)"}.

**Never read by this page** — {", ".join(f"`{f}`" for f in sealed_here) or
"`keyring.jsonl`, `name_key.json`, `access_ledger.json` (none present here)"}.
These are gitignored and are not committed to this repository.

**The honest limits.** Streamlit Community Cloud has no per-user authentication
that an app can rely on, so this is a shared-password gate: it stops casual
access and signals that the data is for public-safety and non-discriminatory
research, but anyone given the password can copy what they see. It is not a
substitute for an audited, per-requester access process. Selling names would
also raise FCRA questions if a buyer used them for employment, tenancy or credit
screening — see `data/arrests/README.md`.
"""
        )
    st.stop()

serve()
