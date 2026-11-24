"""Action items & decisions — verbatim, pattern-categorized, locator-stamped.

Every record stores the FULL source sentence (clipped at 300 chars with an
ellipsis marker) plus the regex category that caught it. The category is a
label on a quote, never a paraphrase: ``python3 -m fireflies verify`` checks
each quote is a verbatim substring of its source text.

Categories: motion | second | outcome | vote-tally | directive | consensus |
scheduling | appointment | adjournment.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

from .textutil import (clip_quote, find_normalized, first_sentence, normalize_ws,
                       ocr_join, split_sentences)

_NAME = r"[A-Z][\w'.\-]+(?:\s+[A-Z][\w'.\-]+){0,3}"

PATTERNS = [
    # name-anchored variants stay CASE-SENSITIVE (so "the second phase" or
    # "we could move to" never pose as a member's motion); phrase variants
    # use scoped case-insensitivity.
    ("motion", re.compile(
        r"(?<![a-z])(" + _NAME + r"|\bI)\s+(?:would\s+)?(?:moved|moves|move)\s+to\s+\S"
        r"|(?i:\bmoved\s+by\s+)(" + _NAME + r")"
        r"|(?i:\bmotion\s+(?:was\s+)?(?:made\s+)?by\s+)(" + _NAME + r")"
        r"|(?i:\b(?:i|we)\s+(?:would\s+)?move\s+to\s+\S)")),
    ("second", re.compile(
        r"(?i:\bseconded?\s+by\s+)(\S+(?:\s+\S+)?)"
        r"|\bI(?:'ll| will)?\s+(?:would\s+)?second\b"
        r"|(?<![a-z])(?:Mr|Mrs|Ms|Dr|Prof)\.?\s+(" + _NAME + r")\s+(?:would\s+)?second\b"
        r"|(?<![a-z])(" + _NAME + r")(?:\s+[A-Z][\w'.\-]+){0,2}\s+(?:would\s+)?second\b")),
    ("outcome", re.compile(
        r"(?i)(motion\s+(?:carried|passed|failed|was\s+approved|was\s+defeated|prevails|carries)"
        r"|carried\s+unanimous(?:ly)?|unanimous(?:ly)?\s+(?:approved|carried)"
        r"|motion\s+to\s+\w+\s+(?:was\s+)?(?:carried|approved|failed)"
        r"|recommendation\s+(?:for\s+\w+\s+night\s+)?will\s+be\s+to\s+\w+)")),
    ("vote-tally", re.compile(
        r"(?i)(voting\s+[“\"]yes[”\"]\s*[–—-]\s*[^.]{0,200}"
        r"|vot(?:ing|ed)\s+no\b[^.]{0,120}"
        r"|all\s+in\s+favor\s+(?:signify\s+by\s+saying|say)\s*(?:I|aye)[^.]{0,120}"
        r"|(?:passed|carried|approved)\s+\(?(\d+)\s*[–—-]\s*(\d+)\)?)")),
    ("directive", re.compile(
        r"(?i)((?:staff|they|the\s+department)\s+(?:was|were|is|are|will\s+be)?\s*"
        r"(?:directed|instructed|asked|authorized)\s+to\s+[^.]{5,200}"
        r"|directed\s+staff\s+to\s+[^.]{5,200}"
        r"|instructed\s+staff\s+to\s+[^.]{5,200}"
        r"|staff\s+will\s+[^.]{5,200}"
        r"|bring\s+(?:it|this|an?\s+\w+)\s+back\s+[^.]{0,160})")),
    ("consensus", re.compile(
        r"(?i)(consensus\s+of\s+the\s+(?:committee|commission|governing\s+body|council)\s*"
        r"(?:was|is)?\s*(?:to\s+)?[^.]{5,200}"
        r"|it\s+was\s+the\s+consensus\s+[^.]{5,200})")),
    ("scheduling", re.compile(
        r"(?i)((?:item\s+was\s+)?tabled\s+(?:until|to|indefinitely)?[^.]{0,120}"
        r"|(?:continue[d]?|continued|held\s+over|postponed)\s+(?:to|until)\s+[^.]{0,120}"
        r"|public\s+hearing\s+(?:was\s+)?set\s+(?:for\s+)?[^.]{0,120}"
        r"|set\s+(?:for\s+)?(?:a\s+)?public\s+hearing\s+(?:for\s+|on\s+)?[^.]{0,120}"
        r"|will\s+come\s+back\s+(?:to|before)\s+[^.]{0,120})")),
    ("appointment", re.compile(
        r"(?i)((?:appointed|elected|nominated|reappointed|sworn\s+in)\s+[^.]{0,160}"
        r"|(?:appointment|election|nomination)\s+of\s+[^.]{0,160})")),
    ("adjournment", re.compile(
        r"(?i)(meeting\s+(?:was\s+)?adjourned[^.]{0,80}|recessed\s+(?:until|at)\s+[^.]{0,80})")),
]

# Patterns that must NOT alone classify a sentence (ambiguous phrases)
_GUARD = re.compile(r"(?i)\b(i think|i believe|would have|if we|we should|we could|maybe)\b")

# words that can never be a member's name in the who slot ("The second phase…")
_BAD_WHO = set("""
the a an this that it if when where but and so then here there his her their our
my your we they you second next last first other another both each few most some
such no nor not only own same too very can will just should now all any every
after before during while about against between through under over once also
even still yet ever never always hearing seeing however moreover further yes
yeah okay well second phase
""".split())


@dataclass
class Action:
    type: str
    quote: str                 # verbatim source sentence (clipped, ellipsis marks cut)
    who: str = ""              # matched name, if any
    locator: dict = field(default_factory=dict)
    item_id: str = ""
    pattern: str = ""


def _locate(text: str, sent: str, kind: str, ref: str, segments, start_hint=0) -> dict:
    idx = find_normalized(text, sent, start_hint)
    if idx < 0:
        idx = find_normalized(text, sent)
    loc = {"kind": kind, "ref": ref, "char": max(idx, 0)}
    if kind == "asr" and segments:
        ts = ""
        for s in segments:
            if s["start"] <= idx:
                ts = f"{s['t']//3600:02d}:{(s['t']%3600)//60:02d}:{s['t']%60:02d}"
            else:
                break
        loc["ts"] = ts
    elif kind == "minutes":
        loc["para"] = text[:max(idx, 0)].count("\n\n") + 1
    return loc


def extract_actions(text: str, kind: str, ref: str, segments: list = None) -> list:
    """Scan a source text; one Action per (sentence, first matching category)."""
    out: list = []
    seen = set()
    pos = 0
    for sent in split_sentences(text):
        body = normalize_ws(sent)
        if not (12 <= len(body) <= 400):
            continue  # too short to be evidence / too long to be one sentence
        probe = ocr_join(body)
        for cat, rx in PATTERNS:
            m = rx.search(probe)
            if not m:
                continue
            if cat in ("motion", "second") and _GUARD.search(probe) and "moved to" not in probe.lower():
                continue
            who = ""
            for g in m.groups():
                cand = (g or "").strip().rstrip(".,;:")
                if cand and re.fullmatch(_NAME, cand) and cand.lower() != "i":
                    who = cand
                    break
            if cat in ("motion", "second") and who.lower() in _BAD_WHO:
                continue  # article/pronoun posing as a member's name
            if cat == "second" and not who and not re.search(
                    r"(?i:seconded?\s+by)|\bI(?:'ll| will)?\s+(?:would\s+)?second\b",
                    probe):
                continue
            key = (cat, body[:160])
            if key in seen:
                break
            seen.add(key)
            out.append(Action(
                type=cat,
                quote=clip_quote(body),
                who=who,
                locator=_locate(text, body, kind, ref, segments, pos),
                pattern=rx.pattern[:60],
            ))
            found = find_normalized(text, body, pos)
            pos = (found + 1) if found >= 0 else pos
            # a sentence can carry several decision types (a motion that is
            # seconded in the same sentence yields both records)
    return out


def attendance_quote(text: str, kind: str, ref: str) -> dict:
    """Verbatim attendance/roll-call span from minutes prose, if present."""
    if kind not in ("minutes", "md"):
        return {}
    norm = normalize_ws(text)
    m = re.search(r"(?i)\bPresent were:", norm)
    if m:
        q = clip_quote(first_sentence(norm[m.start():], 500), 450)
        return {"quote": q, "locator": {"kind": kind, "ref": ref, "char": 0}}
    m = re.search(r"(?i)\broll call\b", norm)
    if m:
        q = clip_quote(first_sentence(norm[m.start():], 500), 450)
        return {"quote": q, "locator": {"kind": kind, "ref": ref, "char": 0}}
    return {}
