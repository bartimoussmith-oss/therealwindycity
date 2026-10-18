"""Ingest-time redaction for arrest-log captures.

WHY THIS EXISTS
---------------
The owner publishes arrest records de-identified and gates names behind a
password / paid access code. That gate is only real if the names never reach the
public repo in the first place. As of 2026-10-17 they already had: one capture
was committed to data/snapshots/, data/text/ and data/engine.db (all tracked,
all public). This module stops that happening again.

It is deliberately fail-CLOSED. If a document is recognised as an arrest log and
redaction cannot provably remove every person name, the capture is refused
rather than committed. Leaking a name is worse than losing a snapshot.

WHAT IT DOES NOT DO
-------------------
It does not reach back into git history, and it does not rewrite captures that
are already committed -- repo protocol forbids force-pushing or resetting the
remote, and the engine's provenance (verify_vault.py greps claims against this
captured text) depends on those files. Already-public names stay public; see
data/arrests/README.md "Honesty".

Person names found here are appended to a SEALED keyring that is gitignored and
never committed: data/arrests/keyring.jsonl.
"""

from __future__ import annotations

import hashlib
import html as _html
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ARREST_DIR = ROOT / "data" / "arrests"
KEYRING = ARREST_DIR / "keyring.jsonl"

REPLACEMENT = "[WITHHELD]"

# An arrest-log capture: the weekly compiled log published by local news.
ARREST_HINT = re.compile(r"arrest[- _]?report|weekly arrest log", re.I)

# A bare date-range section header, e.g. 8/28/26-8/31/26 -- never a name.
DATE_RANGE = re.compile(
    r"^\d{1,2}/\d{1,2}/\d{2,4}\s*[\u2013\u2014-]\s*\d{1,2}/\d{1,2}/\d{2,4}$"
)

# One log entry: Name <en/em-dash> charge, charge
ENTRY = re.compile(r"^(?P<name>.+?)\s*[\u2013\u2014]\s*(?P<charges>.+)$")

# A person name: 2-6 capitalised tokens, letters/apostrophes/periods/hyphens
# only, optional generational suffix. No digits, no parentheses, no URLs.
NAME_SHAPE = re.compile(
    r"^[A-Z][A-Za-z'\u2019.\-]+"
    r"(?:\s+[A-Z][A-Za-z'\u2019.\-]+){1,5}"
    r"(?:\s+(?:Jr\.?|Sr\.?|II|III|IV))?$"
)

# Suffixes and particles that are not distinctive on their own.
_NAME_STOP = {"jr", "sr", "ii", "iii", "iv", "st", "mr", "mrs", "ms", "de", "la"}

# Body bounds inside the extracted text.
BODY_START = re.compile(r"compiled arrest logs", re.I)
BODY_END = re.compile(r"^(Related|More by|Popular|Search for:|Search|Tags?)$")


class RedactionError(RuntimeError):
    """Raised when a name cannot be provably removed. Capture must be refused."""


def is_arrest_document(url: str = "", title: str = "") -> bool:
    """True when a document is an arrest log whose names must be withheld."""
    return bool(ARREST_HINT.search(url or "") or ARREST_HINT.search(title or ""))


def _visible_lines(raw: str) -> list[str]:
    """HTML -> visible text lines. Plain text passes through unchanged."""
    if "<" in raw and ">" in raw:
        body = re.sub(
            r"<script.*?</script>|<style.*?</style>|<nav.*?</nav>"
            r"|<header.*?</header>|<footer.*?</footer>",
            "", raw, flags=re.S | re.I,
        )
        text = _html.unescape(re.sub(r"<[^>]+>", "\n", body))
    else:
        text = raw
    return [ln.strip() for ln in text.split("\n") if ln.strip()]


def find_person_names(raw: str) -> list[str]:
    """Every person name in an arrest-log capture, in document order, deduped.

    Restricted to the article body so headlines, navigation and author bylines
    are never mistaken for arrest subjects.
    """
    lines = _visible_lines(raw)
    start = next((i for i, ln in enumerate(lines) if BODY_START.search(ln)), None)
    if start is None:
        # No lede: fall back to the whole document but keep the strict shape test.
        start = 0
    names: list[str] = []
    seen: set[str] = set()
    for ln in lines[start:]:
        if BODY_END.match(ln):
            break
        if DATE_RANGE.match(ln):
            continue
        m = ENTRY.match(ln)
        if not m:
            continue
        cand = m.group("name").strip()
        if NAME_SHAPE.match(cand) and cand not in seen:
            seen.add(cand)
            names.append(cand)
    return names


def _redact_string(text: str, names: list[str]) -> str:
    """Replace every occurrence of every name. Longest first, so a name that is
    a prefix of another (Ricky J. Gadbaw Sr. / Ricky Joe Gadbaw Jr.) cannot leave
    a fragment behind."""
    for nm in sorted(names, key=len, reverse=True):
        text = text.replace(nm, REPLACEMENT)
    return text


def redact_text(content: str, url: str = "", title: str = "") -> tuple[str, list[str]]:
    """Redact extracted text. Returns (redacted_content, names).

    Raises RedactionError if any name survives -- fail closed.
    """
    names = find_person_names(content)
    if not names:
        return content, []
    out = _redact_string(content, names)
    survivors = [n for n in names if n in out]
    if survivors:
        raise RedactionError(
            f"{len(survivors)} name(s) survived text redaction for "
            f"{title or url or '<capture>'}"
        )
    return out, names


def redact_bytes(raw: bytes, url: str = "", title: str = "") -> tuple[bytes, list[str]]:
    """Redact a captured HTML/binary page. Returns (redacted_bytes, names).

    Names are located in the extracted text (reliable) and then removed from the
    raw bytes by exact-string replacement, which preserves every tag, attribute
    and byte of surrounding markup. Raises RedactionError if any name survives.
    """
    text = raw.decode("utf-8", errors="replace")
    names = find_person_names(text)
    if not names:
        return raw, []
    out = _redact_string(text, names)
    survivors = [n for n in names if n in out]
    if survivors:
        raise RedactionError(
            f"{len(survivors)} name(s) survived snapshot redaction for "
            f"{title or url or '<capture>'}"
        )
    return out.encode("utf-8"), names


def seal_names(names: list[str], *, url: str = "", title: str = "",
               source: str = "", capture: str = "") -> Path:
    """Append withheld names to the SEALED keyring (gitignored, mode 600).

    The keyring is the owner-side record of what was removed and from where, so
    the full tier can be reconstructed offline. It is never committed.
    """
    if not names:
        return KEYRING
    ARREST_DIR.mkdir(parents=True, exist_ok=True)
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    src_sha = hashlib.sha256((url or capture or title).encode()).hexdigest()[:16]
    fresh = not KEYRING.exists()
    with KEYRING.open("a", encoding="utf-8") as fh:
        for i, nm in enumerate(names, start=1):
            fh.write(json.dumps({
                "sealed_at": now,
                "record_ref": f"{src_sha}-{i:03d}",
                "name": nm,
                "source": source,
                "url": url,
                "title": title,
                "capture": capture,
            }, ensure_ascii=False, sort_keys=True) + "\n")
    os.chmod(KEYRING, 0o600)
    if fresh:
        _ensure_ignored()
    return KEYRING


def _ensure_ignored() -> None:
    """Safety net: if the keyring is not gitignored, say so loudly. Never let a
    sealed file become committable by accident."""
    gi = ROOT / ".gitignore"
    pat = "/data/arrests/keyring.jsonl"
    if gi.exists() and pat in gi.read_text():
        return
    raise RedactionError(
        f"{pat} is missing from .gitignore - refusing to write the sealed "
        f"keyring where git could commit it"
    )


def keyring_count() -> int:
    if not KEYRING.exists():
        return 0
    return sum(1 for ln in KEYRING.read_text(encoding="utf-8").split("\n") if ln.strip())
