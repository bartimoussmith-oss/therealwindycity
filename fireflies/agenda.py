"""Agenda item extraction — three evidence grades, each method-tagged:

  1. Granicus agenda HTML (pipeline/docs/*/_agenda.html): numbered items with
     ACTION lines and Supporting Document links (granicus-agenda-html-v1).
  2. Minutes prose (RECORD OF PROCEEDINGS): item paragraphs matched against
     the clerk's item leads — ORDINANCE / RESOLUTION / [CA] / PUBLIC HEARING…
     (minutes-item-patterns-v1).
  3. Speech cues in captions/markdown transcripts: "next item please number 9
     ordinance third reading…" (speech-item-cues-v1). Titles derived from
     speech are labelled ``title_guess``; the verbatim cue sentence is always
     kept as the quote.

Merging across sources happens in build.py. Nothing here paraphrases: titles
come from the source text itself.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .textutil import (find_normalized, normalize_ws, ocr_join, split_sentences,
                       strip_tags, unescape_html)

# ------------------------------------------------------------------ model

@dataclass
class AgendaItem:
    item_id: str = ""
    title: str = ""              # verbatim from source (or cue-derived guess)
    title_guess: bool = False    # True when derived from speech cue
    quote: str = ""              # verbatim source span backing the title
    kind: str = "other"
    reading: str = ""            # 1st/2nd/3rd reading for ordinances
    number: str = ""             # ordinance / resolution number when present
    expected_action: str = ""    # agenda-HTML ACTION line, verbatim
    item_no: str = ""            # agenda number (e.g. '8', '8b', '20D')
    locator: dict = field(default_factory=dict)   # {kind, ref, start, end, page, para}
    docs: list = field(default_factory=list)      # {title, ref, url}
    method: str = ""


# ------------------------------------------------------- shared classifiers

_ITEM_LEADS = re.compile(
    r"^\s*(?:\[CA\]\s*)?(?:"
    r"ORDINANCE|AN ORDINANCE|RESOLUTION|A RESOLUTION|PUBLIC HEARING|"
    r"AMENDMENT TO|APPOINTMENTS?\s|ITEM\s+\d|AGENDA ITEM|"
    r"LEASES?/CONTRACTS|CONTRACT MODIFICATIONS?\b|CONSIDERATION\b|"
    r"MINUTES FROM|MINUTES OF|"
    r"AGREEMENT\b|CONTRACT\b|LEASE\b|MEMORANDUM OF UNDERSTANDING|"
    r"BID\b|AWARD\b|CHANGE ORDER|ORDINANCE –|ORDINANCE -|ORDINANCE —"
    r")",
    re.I,
)

_READING = re.compile(r"(\d(?:st|nd|rd|th))\s*READING", re.I)
_ORD_NO = re.compile(r"\bORDINANCE(?:\s+NO\.?|\s+NUMBER)?\s*(\d{3,5})\b", re.I)
_RES_NO = re.compile(r"\bRESOLUTION(?:\s+NO\.?|\s+NUMBER)?\s*(\d{3,5})\b", re.I)


def classify_title(title: str) -> str:
    t = title.strip()
    tl = t.lower()
    if tl.startswith("[ca] minutes") or tl.startswith("minutes from") or tl.startswith("minutes of"):
        return "minutes"
    if tl.startswith("[ca]") or "consent agenda" in tl[:60]:
        return "consent"
    if re.match(r"^(an )?ordinance", tl) or tl.startswith("ordinance"):
        return "ordinance"
    if re.match(r"^(a )?resolution", tl):
        return "resolution"
    if tl.startswith("public hearing"):
        return "hearing"
    if re.search(r"appointment|nomination|election of|oath of office", tl):
        return "appointment"
    if re.search(r"contract|agreement|lease|memorandum of understanding|change order|"
                 r"professional services|maintenance|award|bid", tl):
        return "contract"
    if re.search(r"budget|fiscal|tax|fee schedule|appropriat", tl):
        return "finance"
    if re.search(r"zoning|annex|plat|subdivision|permit|land use|comprehensive plan", tl):
        return "land-use"
    return "other"


def _number_and_reading(title: str) -> tuple:
    reading = ""
    m = _READING.search(title)
    if m:
        w = m.group(1).lower()
        reading = {"1st": "1st", "2nd": "2nd", "3rd": "3rd", "1st": "1st"}.get(w, w)
    number = ""
    m = _ORD_NO.search(title) or _RES_NO.search(title)
    if m:
        number = m.group(1)
    return number, reading


# --------------------------------------------------------- 1. agenda HTML

_ANCHOR = re.compile(r"<a\s+([^>]*)>(.*?)</a>", re.S | re.I)


def _html_lines(html_fragment: str) -> str:
    """Tag-stripped text that KEEPS line structure (so ACTION: lines stay
    single lines). Whitespace inside a line is normalized."""
    txt = re.sub(r"(?i)<(br|/tr|/p|/div|/h[1-6]|/li)[^>]*>", "\n", html_fragment)
    txt = re.sub(r"<[^>]+>", " ", txt)
    txt = unescape_html(txt)
    lines = [normalize_ws(l) for l in txt.splitlines()]
    return "\n".join(l for l in lines if l)


def parse_agenda_html(html_text: str, ref: str = "") -> list:
    """Parse Granicus AgendaViewer HTML into AgendaItems with doc links."""
    items: list = []
    current: AgendaItem = None
    tail_text = ""     # text between anchors, for ACTION lines
    pending_docs: list = []

    def flush_tail():
        nonlocal tail_text, pending_docs
        if current is not None:
            m = re.search(r"(?m)^ACTION:[ \t]*(.*)", tail_text)
            if m and not current.expected_action:
                before = tail_text[:m.start()]
                # an unanchored sub-item ("8.", "a)") before the ACTION line
                # means the action belongs to that sub-item, not to current
                if not re.search(r"(?m)^\s*(?:\d+\.\s|[a-z]\)\s|ITEM\s+\d)", before):
                    current.expected_action = normalize_ws(m.group(1))[:200]
            if pending_docs:
                current.docs.extend(pending_docs)
                pending_docs = []
        tail_text = ""

    last_end = 0
    for m in _ANCHOR.finditer(html_text):
        # the span BEFORE this anchor belongs to the item current at span time:
        # accumulate it, flush to that item, then process the new anchor
        span_text = html_text[last_end:m.start()]
        tail_text += "\n" + _html_lines(span_text)
        flush_tail()
        last_end = m.end()
        attrs, inner = m.group(1), m.group(2)
        label = normalize_ws(strip_tags(unescape_html(inner)))
        href = ""
        hm = re.search(r'href="([^"]+)"', attrs)
        if hm:
            href = hm.group(1)
        nm = re.search(r'name="(agenda|document)(\d+)"', attrs)
        if not nm:
            continue
        if nm.group(1) == "agenda":
            if not label:
                continue
            title = label
            if title.upper().startswith("CONSENT AGENDA") and (
                    "designation" in title.lower() or "designated" in title.lower()):
                # consent-agenda preamble block: keep it as a section header
                title = "CONSENT AGENDA."
            number, reading = _number_and_reading(title)
            current = AgendaItem(
                title=title, quote=title,
                kind=classify_title(title), reading=reading, number=number,
                locator={"kind": "agenda_html", "ref": ref,
                         "anchor": f"agenda{nm.group(2)}", "url": href},
                method="granicus-agenda-html-v1",
            )
            if href:
                current.docs.append({"title": f"video: {title[:60]}",
                                     "ref": "", "url": href, "kind": "video-link"})
            items.append(current)
        else:  # document link
            doc = {"title": label or "Supporting Document", "ref": "",
                   "url": href, "kind": "packet"}
            if current is not None:
                current.docs.append(doc)
            else:
                pending_docs.append(doc)
    flush_tail()
    return items


# ---------------------------------------------------------- 2. minutes prose

def parse_minutes_items(text: str, ref: str = "") -> list:
    """Sentence-scan RECORD OF PROCEEDINGS text for item leads.

    Old PDF-era minutes pack several items into one paragraph, so every
    sentence is checked for an item lead, not just the first per paragraph.
    """
    items: list = []
    para_idx = 0
    page = ""
    for block in re.split(r"\n\s*\n", text):
        block = block.strip()
        if not block:
            continue
        para_idx += 1
        pm = re.match(r"^(\d{1,3})$", block.strip())
        if pm:
            page = pm.group(1)
            continue
        for sent in split_sentences(block):
            probe = ocr_join(sent)
            if not _ITEM_LEADS.match(probe):
                continue
            title = normalize_ws(sent)[:300]
            number, reading = _number_and_reading(probe)
            item = AgendaItem(
                title=title,
                quote=title,
                kind=classify_title(probe),
                reading=reading, number=number,
                locator={"kind": "minutes", "ref": ref, "para": para_idx, "page": page},
                method="minutes-item-patterns-v1",
            )
            items.append(item)
    return items


# ------------------------------------------------------- 3. speech cues

_CUE = re.compile(
    r"(?i)\b((?:next|first|second|third|following|final|last)\s+item"
    r"(?:\s+please)?(?:\s+is)?|agenda item)"
    r"\s*(?:number\s+|no\.?\s*|#\s*)?"
    r"(\d+[A-Za-z]?(?:\([a-z]\))?)?\b"
)

_CUE_NOUNS = re.compile(
    r"(?i)\b(ordinance|resolution|agreement|contract|lease|minutes|"
    r"public hearing|memorandum|modification|consideration|appointment|bid|award)\b")

_TITLE_CUT = re.compile(r"(?i)\b(staff report|please|and the staff|could I have)\b")


def parse_speech_items(text: str, ref: str = "", segments: list = None) -> list:
    """Find agenda-item cues in caption/markdown speech. Quote = full sentence."""
    items: list = []
    # char offset -> timestamp lookup for ASR
    seg_starts = [(s["start"], s["t"]) for s in (segments or [])]

    def ts_at(pos):
        ts = ""
        for start, t in seg_starts:
            if start <= pos:
                ts = f"{t//3600:02d}:{(t%3600)//60:02d}:{t%60:02d}"
            else:
                break
        return ts

    for sent in split_sentences(text):
        probe = ocr_join(normalize_ws(sent))
        for m in _CUE.finditer(probe):
            if m.start() > 60:
                continue  # item cues announce — they open the sentence
            item_no = (m.group(2) or "").strip()
            after = probe[m.end():]
            has_noun = bool(_CUE_NOUNS.search(after[:100]))
            if not has_noun and not (item_no and item_no[-1:].isalpha()
                                     and _CUE_NOUNS.search(probe)):
                continue  # procedural "item 3" mentions are not agenda items
            guess = after.strip(" .,:")
            guess = re.sub(r"(?i)^(?:please|number|no\.?|#)\s*[a-z0-9]*[.,:]*\s*",
                           "", guess, count=1)
            cut = _TITLE_CUT.search(guess)
            if cut:
                guess = guess[:cut.start()]
            guess = normalize_ws(re.sub(r"\[\d{1,2}:\d{2}:\d{2}\]", "", guess))[:220]
            quote = normalize_ws(sent)
            pos = find_normalized(text, sent)
            number, reading = _number_and_reading(quote)
            title_txt = normalize_ws(re.sub(
                r"\[\d{1,2}:\d{2}:\d{2}\]", "", guess or quote[:160]))
            item = AgendaItem(
                title=title_txt,
                title_guess=bool(guess),
                quote=quote,
                kind=classify_title(guess or quote),
                reading=reading, number=number, item_no=item_no,
                locator={"kind": "speech", "ref": ref,
                         "char": pos if pos >= 0 else 0,
                         "ts": ts_at(pos if pos >= 0 else 0)},
                method="speech-item-cues-v1",
            )
            items.append(item)
            break  # one cue per sentence
    return items


def extract_items(text: str, kind: str, ref: str, segments: list = None) -> list:
    """Dispatch by source kind."""
    if kind == "agenda_html":
        return parse_agenda_html(text, ref)
    if kind == "minutes":
        return parse_minutes_items(text, ref)
    return parse_speech_items(text, ref, segments)
