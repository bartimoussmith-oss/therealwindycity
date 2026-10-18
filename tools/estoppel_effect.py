#!/usr/bin/env python3
"""Source-aware, deterministic research aid for the practical "estoppel effect".

The program detects *candidate* record-building tactics and ranks possible
same-meeting/source-check and cross-meeting chronology links. It does not
classify a legal violation, establish that speakers relied on a statement,
prove a contradiction, or infer causation or estoppel.

Default inputs:
  pipeline/miller_interventions.json       caption-aligned Miller cue blocks
  drive-import/master_meetings_database.json.gz  meeting-level caption corpus

Example:
  python tools/estoppel_effect.py \
      --out /tmp/estoppel-effect-audit.json \
      --review-csv /tmp/estoppel-effect-review.csv

Stdlib only. The meeting database normalizer is shared with the AI-readable
record build (tools/ai_record_drive.py); source files are never modified.
"""
from __future__ import annotations

import argparse
import bisect
import collections
import csv
import datetime as dt
import hashlib
import json
import math
import re
from pathlib import Path
from typing import Any, Iterable

ALGORITHM_VERSION = "1.0.0"
SCHEMA_VERSION = "1"
DEFAULT_INTERVENTIONS = "pipeline/miller_interventions.json"
DEFAULT_MEETINGS_DB = "drive-import/master_meetings_database.json.gz"

# Patterns are intentionally conservative phrase signals. A match is a review
# lead, not a finding that the tactic was used successfully or legally.
TACTIC_RULES: dict[str, tuple[str, ...]] = {
    "assurance_to_instrument": (
        r"\b(?:nothing|no thing)\s+(?:will|would|can|should)\s+(?:change|be different)\b",
        r"\b(?:will|would|can|could|should)\s+not\s+(?:change|alter|affect)\b",
        r"\b(?:will|would|can|could)\s+(?:continue|remain|stay|operate|use|be permitted|be allowed)\b",
        r"\bgrandfather(?:ed|ing)?\b|\bvested rights?\b",
        r"\b(?:assurance|assure|guarantee|commitment|promise)\b",
        r"\b(?:written|adopted|binding|legal)\s+(?:protection|determination|commitment|assurance|instrument|text)\b",
        r"\b(?:identify|cite|point to|provide)\b.{0,80}\b(?:adopted (?:text|provision)|ordinance|code|section|permit|agreement|determination|instrument|protection)\b",
    ),
    "predecision_evidence_gap": (
        r"\b(?:not in|missing from|absent from|not included in)\b.{0,45}\b(?:record|packet|materials|agenda|submission|file)\b",
        r"\b(?:could not|couldn't|cannot|can't|unable to)\s+(?:find|locate|review|access)\b.{0,70}\b(?:report|analysis|study|data|document|record|packet)\b",
        r"\bmissing\b.{0,55}\b(?:report|analysis|study|data|feasibility|findings|document)\b",
        r"\b(?:before|prior to)\b.{0,65}\b(?:findings?|decision|vote|action)\b.{0,90}\b(?:report|analysis|evidence|study|data|feasibility)\b",
        r"\b(?:no|without)\s+(?:supporting )?(?:report|analysis|study|feasibility|evidence)\b",
    ),
    "analytical_bridge": (
        r"\b(?:basis|evidence|analysis|reasoning)\b.{0,60}\b(?:for|support(?:s|ing)?)\b.{0,30}\b(?:finding|conclusion|criterion|decision)\b",
        r"\b(?:what|which)\s+(?:evidence|analysis|finding|criterion|criteria|basis)\b",
        r"\bhow\s+(?:does|do|is|are)\b.{0,55}\b(?:support|connect|show|meet|satisfy)\b",
        r"\b(?:connect|connection|bridge)\b.{0,50}\b(?:evidence|criteria|finding|decision)\b",
        r"\b(?:findings of fact|specific findings|articulated findings)\b",
    ),
    "cross_speaker_comparison": (
        r"\b(?:same|different|unequal)\s+(?:rule|standard|time|treatment|opportunity|restriction|relevance test)\b",
        r"\bviewpoint discrimination\b",
        r"\b(?:proponents?|opponents?|supporters?|critics?)\b.{0,90}\b(?:same|different|allowed|permitted|time|comment|treatment|rule)\b",
        r"\bother\s+(?:speaker|commenter|participant)\b.{0,80}\b(?:allowed|permitted|given|time|rule|standard|speak)\b",
    ),
    "operative_text_narrowing": (
        r"\b(?:move|motion|propose|request)\s+to\s+amend\b",
        r"\b(?:amend|strike|remove|delete|replace|substitute)\b.{0,85}\b(?:word|phrase|language|section|clause|text|provision|term)\b",
        r"\b(?:add|insert)\b.{0,45}\b(?:language|phrase|text|clause|wording)\b",
        r"\b(?:remove|strike)\s+[\"'“][^\"'”]{1,100}[\"'”]",
    ),
    "cross_meeting_chronology": (
        r"\b(?:last|previous|prior|earlier|past)\s+(?:meeting|hearing|work session|vote|record|statement|assurance|commitment)\b",
        r"\b(?:on|at)\s+(?:the\s+)?(?:last|previous|prior)\s+(?:occasion|meeting)\b",
        r"\b(?:you|staff|the city|the council|the board)\s+(?:said|stated|told|promised|represented)\b.{0,90}\b(?:before|last|previous|earlier|again|now)\b",
        r"\b(?:as|like)\s+(?:i|we)\s+(?:said|stated|asked|noted|discussed)\s+(?:last time|previously|before)\b",
        r"\b(?:changed|change)\s+(?:its|the|your)\s+(?:position|explanation|assurance|commitment)\b",
        r"\b(?:previously|earlier you said|you said before|same representation)\b",
    ),
    "notice_opportunity_to_cure": (
        r"\bformal constructive notice\b",
        r"\bconstructive notice\b",
        r"\bfor the (?:permanent |administrative |public )?record\b",
        r"\bplease\b.{0,45}\b(?:correct|revise|clarify|provide|identify|enter|post|preserve|produce)\b",
        r"\b(?:i|we)\s+(?:request|ask)\b.{0,60}\b(?:correct|revise|clarify|provide|identify|enter|post|preserve|produce)\b",
        r"\bopportunity to cure\b",
        r"\bnotice and opportunity to\b.{0,35}\b(?:respond|correct|cure)\b",
    ),
    "fiscal_explanation_testing": (
        r"\b(?:no funds|no money|lack of funding|unavailable funding|budget constraints?|fiscal constraints?|limited resources?)\b",
        r"\b(?:funds?|funding|appropriation|expenditure|reserve|budget)\b.{0,90}\b(?:available|restricted|earmarked|spent|allocated|allocation|priority|priorities|competing|another)\b",
        r"\b(?:spending|funding|appropriation)\b.{0,90}\b(?:priority|priorities|competing|available|restricted|earmarked)\b",
    ),
    # These three are diagnostic cues for a human reviewer, not additional
    # tactics and not legal-element checkers.
    "legal_claim_marker": (
        r"\babsolute estoppel\b|\bestoppel\b|\bqualified immunity\b",
        r"\b(?:42\s+u\.?s\.?c\.?|section)\s*§?\s*1983\b",
        r"\bdeliberate indifference\b",
    ),
    "decision_action_marker": (
        r"\b(?:motion|amendment|ordinance|resolution)\b.{0,55}\b(?:passed|failed|carried|adopted|approved|denied|postponed|rejected)\b",
        r"\b(?:approved|adopted|denied|rejected|postponed)\b.{0,45}\b(?:motion|amendment|ordinance|resolution|item|proposal)\b",
        r"\b(?:voted|vote)\b.{0,45}\b(?:yes|no|in favor|against|approved|rejected)\b",
    ),
    "reliance_prejudice_cue": (
        r"\b(?:relied on|reliance|invested|investment|changed (?:my|our|their) position|detriment|prejudice|injury|damages)\b",
    ),
}
COMPILED_RULES = {
    tag: tuple(re.compile(pattern, re.IGNORECASE) for pattern in patterns)
    for tag, patterns in TACTIC_RULES.items()
}
TACTIC_TAGS = frozenset({
    "assurance_to_instrument", "predecision_evidence_gap", "analytical_bridge",
    "cross_speaker_comparison", "operative_text_narrowing",
    "cross_meeting_chronology", "notice_opportunity_to_cure",
    "fiscal_explanation_testing",
})

WORD_RE = re.compile(r"\S+")
ISSUE_TOKEN_RE = re.compile(r"(?u)[a-z0-9][a-z0-9'-]{1,}")
NEGATION_RE = re.compile(
    r"\b(?:not|no|never|without|cannot|can't|won't|wouldn't|doesn't|didn't|failed to|rejected|denied)\b",
    re.IGNORECASE,
)
ISSUE_STOPWORDS = set("""
a an the and or but if then when while of at by for with about into over after
before between through during above below up down out off on in to from as is
are was were be been being am have has had having do does did doing would could
should may might must shall will can just very really quite so such yes yeah uh
um ah er oh well hey hi hello thank thanks please okay right now today tonight
here there where what which who whom whose why how i me my we us our you your
he him his she her it its they them their this that these those than too also
said says saying state states told tell tells asked asks request requests
record notice formal constructive estoppel effect legal law statute official
city council committee board meeting meetings public agenda item items speaker
comment comments time body members member miller charles tonight earlier before
previously today year 2025 2026 2024 2023 2022 2021 2020 2019 2018
ordinance resolution action vote voted motion approved adopt adopted proposal
amendment amending amendment
""".split())
ISSUE_STOPWORDS.update("""
all every each either kind way able know think not last persons residing
health safety welfare protection jennifer throat clears clear hear hearing
ahead speak want administrative permanent record moody's i'm sir readings
""".split())
# Roll-call and parliamentary boilerplate dominates many municipal transcripts.
# Remove recurrent names and voting/formula words from topic matching so they
# cannot make two unrelated agenda items look alike.
ISSUE_STOPWORDS.update("""
mayor mayoral collins alderich aldrich emmons emmens esquibel esabel moody
white wolfe wolf segrave segreave crave laybourn leborn leeborn renie rinne
rainey roybal johnson clerk madam chair chairwoman chairman alderman councilor
councillor member members governing body anyone anybody question questions
answer answers comment comments commenter commenters presentation speaker
speakers public hearing hearings agenda agenda-item agendaitems committee
committees city cities town towns department director staff motion motions
second seconded moved move amendment amendments amended substitute substitutes
ordinance ordinances resolution resolutions approve approved approving approval
adopt adopted adoption pass passed carry carried fail failed vote votes voted
voting favor opposed signify none thank thanks tonight today welcome order
regular special reading first second third final main business next item number
page paragraph section subsection attachment exhibit document documents
""".split())


def sha256_file(path: str | Path) -> str:
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sha256_text(text: str) -> str:
    normalized = " ".join((text or "").split()).casefold()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def normalize_body(value: str | None) -> str | None:
    if not value:
        return None
    text = re.sub(r"\s+", " ", value).strip().casefold()
    mappings = (
        (r"city council|governing body", "city-council"),
        (r"finance committee", "finance-committee"),
        (r"public services committee", "public-services-committee"),
        (r"planning commission", "planning-commission"),
        (r"historic preservation", "historic-preservation-board"),
        (r"board of adjustment", "board-of-adjustment"),
        (r"urban renewal", "urban-renewal-authority"),
        (r"committee of the whole|work session", "work-sessions"),
    )
    for pattern, body in mappings:
        if re.search(pattern, text):
            return body
    slug = re.sub(r"[^a-z0-9]+", "-", text).strip("-")
    return slug or None


def _iso_date(value: Any) -> str | None:
    if not isinstance(value, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", value):
        return None
    try:
        return dt.date.fromisoformat(value).isoformat()
    except ValueError:
        return None


def _row_key(row: dict[str, Any], index: int) -> tuple[str, str, str]:
    group = row.get("dup_group")
    group_key = str(group) if group is not None else f"row-{index}"
    return (str(row.get("video") or "unknown"), str(row.get("block") or "unknown"), group_key)


def _alignment_quality(row: dict[str, Any]) -> tuple[int, float, float, int]:
    # A non-truncated alignment is preferred; among those, prefer the higher
    # lexical alignment score, then the fuller span, then the lower dup rank.
    non_truncated = int(not bool(row.get("truncated_align")))
    score = float(row.get("score") or 0.0)
    duration = float(row.get("dur") or 0.0)
    rank = int(row.get("dup_rank") or 0)
    return non_truncated, score, duration, -rank


def load_intervention_records(
    path: str | Path,
    min_alignment_score: float = 0.80,
    include_context: bool = True,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load source-aligned Miller cue blocks and collapse overlapping variants.

    Rows in each (video, block kind, duplicate-group) are alternative alignments
    of substantially overlapping caption windows, not independent observations.
    The best non-truncated/high-score/full-span row is selected; alternatives are
    retained as lightweight provenance metadata.
    """
    source_path = Path(path)
    rows = json.loads(source_path.read_text(encoding="utf-8"))
    if not isinstance(rows, list):
        raise ValueError("interventions input must be a JSON list")
    groups: dict[tuple[str, str, str], list[dict[str, Any]]] = collections.defaultdict(list)
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            continue
        groups[_row_key(row, index)].append(row)

    selected: list[dict[str, Any]] = []
    skipped_low = 0
    skipped_truncated = 0
    skipped_context = 0
    for key in sorted(groups):
        variants = groups[key]
        winner = max(variants, key=_alignment_quality)
        block = str(winner.get("block") or "unknown")
        if block == "context" and not include_context:
            skipped_context += 1
            continue
        if bool(winner.get("truncated_align")):
            skipped_truncated += 1
            continue
        score = float(winner.get("score") or 0.0)
        if score < min_alignment_score:
            skipped_low += 1
            continue
        video = str(winner.get("video") or "unknown")
        date = _iso_date(winner.get("date"))
        body = normalize_body(str(winner.get("mkind") or ""))
        t0 = float(winner.get("t0") or 0.0)
        t1 = float(winner.get("t1") or t0)
        text = str(winner.get("text") or "")
        record_id = f"{video}:{block}:{winner.get('n', 'x')}:{t0:.1f}"
        source_id = f"miller-cue:{record_id}"
        is_miller = block == "turn"
        variant_refs = []
        for variant in sorted(variants, key=lambda r: int(r.get("dup_rank") or 0)):
            variant_refs.append({
                "n": variant.get("n"),
                "t0": variant.get("t0"),
                "t1": variant.get("t1"),
                "score": variant.get("score"),
                "dup_rank": variant.get("dup_rank"),
                "truncated_align": bool(variant.get("truncated_align")),
                "selected": variant is winner,
            })
        selected.append({
            "source_id": source_id,
            "meeting_id": f"{date or 'unknown'}:{body or 'unknown'}:{video}",
            "date": date,
            "date_source": "city-video-index" if date else "unknown",
            "title": str(winner.get("title") or ""),
            "body": body,
            "source_type": "caption_aligned_intervention_index",
            "source_role": "miller_intervention" if is_miller else "meeting_context_cue",
            "speaker_attribution": (
                "Miller cue label from the intervention compilation; not independently audio-verified"
                if is_miller else
                "Context/interruption cue; speaker is not assigned by this algorithm"
            ),
            "source_path": str(source_path),
            "source_url": f"https://www.youtube.com/watch?v={video}&t={max(0, int(t0))}s",
            "video_id": video,
            "t0": round(t0, 1),
            "t1": round(t1, 1),
            "block_number": winner.get("n"),
            "alignment_score": score,
            "alignment_score_is_probability": False,
            "truncated_align": False,
            "duplicate_group": winner.get("dup_group"),
            "duplicate_variant_count": max(0, len(variants) - 1),
            "duplicate_variants": variant_refs,
            "source_text_sha256": sha256_text(text),
            "text": text,
        })
    stats = {
        "rows_read": len(rows),
        "duplicate_groups": len(groups),
        "selected_records": len(selected),
        "selected_miller_interventions": sum(r["source_role"] == "miller_intervention" for r in selected),
        "selected_context_cues": sum(r["source_role"] == "meeting_context_cue" for r in selected),
        "alignment_alternates_not_counted_as_independent": sum(max(0, len(v) - 1) for v in groups.values()),
        "skipped_low_alignment": skipped_low,
        "skipped_truncated_alignment": skipped_truncated,
        "skipped_context_cues": skipped_context,
        "min_alignment_score": min_alignment_score,
        "deduplication_key": "(video, block, dup_group); highest-quality non-truncated alternative",
    }
    return selected, stats


def load_meeting_context(path: str | Path) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Load the caption database as unattributed meeting context, not testimony."""
    try:
        from .ai_record_drive import load as load_drive_records
    except ImportError:  # direct script execution: python tools/estoppel_effect.py
        from ai_record_drive import load as load_drive_records

    source_path = Path(path)
    records = load_drive_records(str(source_path))
    duplicate_ids: dict[str, list[str]] = collections.defaultdict(list)
    for rec in records:
        if rec.get("dup_of"):
            duplicate_ids[str(rec["dup_of"])].append(str(rec.get("id") or ""))

    output: list[dict[str, Any]] = []
    duplicate_count = 0
    for rec in records:
        if rec.get("dup_of"):
            duplicate_count += 1
            continue
        date = _iso_date(rec.get("date"))
        text = str(rec.get("text") or "")
        record_id = str(rec.get("id") or rec.get("filename") or rec.get("title") or "unknown")
        body = normalize_body(str(rec.get("body") or rec.get("category") or ""))
        output.append({
            "source_id": f"meeting-db:{record_id}",
            "meeting_id": f"{date or 'unknown'}:{body or 'unknown'}:{record_id}",
            "date": date,
            "date_source": rec.get("date_source") or "unknown",
            "title": str(rec.get("title") or ""),
            "body": body,
            "source_type": "caption_transcript_database",
            "source_role": "unattributed_meeting_context",
            "speaker_attribution": "Not assigned per excerpt; this input is a meeting-level normalized transcript",
            "source_path": str(source_path),
            "source_url": None,
            "video_id": None,
            "t0": None,
            "t1": None,
            "block_number": None,
            "alignment_score": None,
            "alignment_score_is_probability": False,
            "truncated_align": False,
            "duplicate_group": None,
            "duplicate_variant_count": len(duplicate_ids.get(record_id, [])),
            "duplicate_record_ids": duplicate_ids.get(record_id, []),
            "source_text_sha256": sha256_text(text),
            "text": text,
        })
    stats = {
        "records_read": len(records),
        "primary_text_records": len(output),
        "exact_duplicate_records_not_counted_as_independent": duplicate_count,
        "date_inferred_from_title": sum(r.get("date_source") == "title" for r in records if not r.get("dup_of")),
        "date_unknown": sum(_iso_date(r.get("date")) is None for r in records if not r.get("dup_of")),
        "speaker_attribution": "not preserved per excerpt by the shared normalizer",
    }
    return output, stats


def _word_index(word_starts: list[int], char_pos: int) -> int:
    if not word_starts:
        return 0
    return max(0, min(len(word_starts) - 1, bisect.bisect_right(word_starts, char_pos) - 1))


def find_signal_hits(text: str) -> list[dict[str, Any]]:
    """Return phrase hits with source-character offsets; do not infer stance."""
    hits: dict[tuple[str, int, int], dict[str, Any]] = {}
    for tag, patterns in COMPILED_RULES.items():
        for pattern in patterns:
            for match in pattern.finditer(text):
                key = (tag, match.start(), match.end())
                hits[key] = {
                    "tag": tag,
                    "matched_text": match.group(0),
                    "start_char": match.start(),
                    "end_char": match.end(),
                }
    return sorted(hits.values(), key=lambda h: (h["start_char"], h["end_char"], h["tag"]))


def extract_events(
    records: Iterable[dict[str, Any]],
    context_before_words: int = 45,
    context_after_words: int = 65,
    cluster_gap_words: int = 70,
    max_cluster_span_words: int = 130,
) -> list[dict[str, Any]]:
    """Extract local, source-linked candidate events from normalized records."""
    events: list[dict[str, Any]] = []
    for record in records:
        text = str(record.get("text") or "")
        if not text.strip():
            continue
        word_matches = list(WORD_RE.finditer(text))
        word_starts = [m.start() for m in word_matches]
        if not word_matches:
            continue
        hits = find_signal_hits(text)
        if not hits:
            continue
        for hit in hits:
            hit["start_word"] = _word_index(word_starts, hit["start_char"])
            hit["end_word"] = _word_index(word_starts, max(hit["start_char"], hit["end_char"] - 1)) + 1
        clusters: list[list[dict[str, Any]]] = []
        current: list[dict[str, Any]] = []
        for hit in hits:
            if (current and
                hit["start_word"] - current[-1]["start_word"] <= cluster_gap_words and
                hit["start_word"] - current[0]["start_word"] <= max_cluster_span_words):
                current.append(hit)
            else:
                if current:
                    clusters.append(current)
                current = [hit]
        if current:
            clusters.append(current)

        for cluster in clusters:
            first_word = min(h["start_word"] for h in cluster)
            last_word = max(h["end_word"] for h in cluster)
            lo = max(0, first_word - context_before_words)
            hi = min(len(word_matches), last_word + context_after_words)
            char_lo = word_matches[lo].start()
            char_hi = word_matches[hi - 1].end()
            excerpt = text[char_lo:char_hi]
            tags = sorted({h["tag"] for h in cluster})
            source_id = str(record.get("source_id") or "unknown-source")
            digest = hashlib.sha256(
                f"{source_id}|{record.get('source_text_sha256')}|{first_word}|{','.join(tags)}".encode("utf-8")
            ).hexdigest()[:20]
            source = {k: v for k, v in record.items() if k != "text"}
            events.append({
                "event_id": f"evt-{digest}",
                "date": record.get("date"),
                "date_source": record.get("date_source"),
                "title": record.get("title"),
                "body": record.get("body"),
                "source_role": record.get("source_role"),
                "source_type": record.get("source_type"),
                "speaker_attribution": record.get("speaker_attribution"),
                "tactic_candidates": [tag for tag in tags if tag in TACTIC_TAGS],
                "diagnostic_markers": [tag for tag in tags if tag not in TACTIC_TAGS],
                "matched_markers": [
                    {k: h[k] for k in ("tag", "matched_text", "start_char", "end_char", "start_word", "end_word")}
                    for h in cluster
                ],
                "evidence_excerpt": excerpt,
                "excerpt_word_range": [lo, hi],
                "excerpt_start_char": char_lo,
                "excerpt_end_char": char_hi,
                "local_negation_marker_present": bool(NEGATION_RE.search(excerpt)),
                "source_text_sha256": record.get("source_text_sha256"),
                "source": source,
                "candidate_status": "pattern match for human review; not a factual or legal finding",
                "legal_effect": "not assessed",
            })
    return sorted(events, key=lambda e: (
        e.get("date") or "9999-99-99", e.get("body") or "", e.get("title") or "",
        e.get("source", {}).get("source_id") or "", e["excerpt_word_range"][0], e["event_id"],
    ))


def _issue_tokens(text: str) -> collections.Counter[str]:
    tokens = []
    for raw in ISSUE_TOKEN_RE.findall((text or "").casefold()):
        token = raw.strip("'-")
        if len(token) < 3 or token in ISSUE_STOPWORDS:
            continue
        if token.isdigit() and (len(token) == 4 and 2008 <= int(token) <= 2027):
            continue
        tokens.append(token)
    return collections.Counter(tokens)


def _cosine(
    left: collections.Counter[str],
    right: collections.Counter[str],
    idf: dict[str, float],
) -> float:
    shared = left.keys() & right.keys()
    dot = sum((1 + math.log(left[t])) * (1 + math.log(right[t])) * idf.get(t, 0.0) ** 2 for t in shared)
    left_norm = math.sqrt(sum(((1 + math.log(n)) * idf.get(t, 0.0)) ** 2 for t, n in left.items()))
    right_norm = math.sqrt(sum(((1 + math.log(n)) * idf.get(t, 0.0)) ** 2 for t, n in right.items()))
    if not left_norm or not right_norm:
        return 0.0
    return dot / (left_norm * right_norm)


def _event_date(event: dict[str, Any]) -> dt.date | None:
    value = _iso_date(event.get("date"))
    return dt.date.fromisoformat(value) if value else None


def _event_video(event: dict[str, Any]) -> str | None:
    return event.get("source", {}).get("video_id")


def _review_fields(relation: str) -> dict[str, Any]:
    return {
        "review_status": "unreviewed",
        "same_issue": "unassessed",
        "same_proposition": "unassessed",
        "same_scope_and_stage": "unassessed",
        "same_authority_or_speaker": "unassessed",
        "material_facts_changed": "unassessed",
        "response_or_cure": "unassessed",
        "contradiction": "unassessed",
        "causal_link": "unassessed",
        "legal_effect": "not assessed",
        "required_review": [
            "confirm the source wording and attribution against original audio or official record",
            "decide whether both excerpts concern the same issue and proposition",
            "compare scope, procedural stage, authority, and intervening facts",
            "record any explanation, correction, amendment, or outcome with its own source",
            "do not treat sequence, silence, or a pattern tag as proof of causation or estoppel",
        ],
        "relation_kind": relation,
    }


def rank_comparison_candidates(
    events: list[dict[str, Any]],
    min_shared_terms: int = 2,
    min_similarity: float = 0.08,
    top_per_miller_event: int = 3,
    max_date_gap_days: int = 3650,
    allow_cross_body: bool = False,
    max_document_frequency_fraction: float = 0.20,
    max_terms_per_event: int = 10,
) -> list[dict[str, Any]]:
    """Rank possible links; all legal/factual conclusions remain unreviewed.

    Three link types are emitted separately:
      * same_meeting_source_crosscheck: cue excerpt ↔ meeting-level transcript
      * same_meeting_sequence_candidate: cue ↔ later context cue on same video
      * cross_meeting_chronology_candidate: date-ordered, same-topic candidates
    """
    if not events:
        return []
    term_counts = [_issue_tokens(e.get("evidence_excerpt", "")) for e in events]
    df: collections.Counter[str] = collections.Counter()
    for counter in term_counts:
        df.update(counter.keys())
    n_docs = max(1, len(events))
    idf = {term: math.log(1 + (n_docs + 1) / (count + 1)) + 1 for term, count in df.items()}
    max_df = max(2, math.ceil(n_docs * max_document_frequency_fraction))

    # Limit each event to its most discriminative terms before building an
    # inverted index. This keeps the candidate generator bounded on large corpora.
    postings: dict[str, list[int]] = collections.defaultdict(list)
    vectors: list[collections.Counter[str]] = []
    for i, counts in enumerate(term_counts):
        usable = {t: c for t, c in counts.items() if df[t] <= max_df}
        selected_terms = sorted(
            usable,
            key=lambda t: ((1 + math.log(usable[t])) * idf[t], t),
            reverse=True,
        )[:max_terms_per_event]
        selected = collections.Counter({t: usable[t] for t in selected_terms})
        vectors.append(selected)
        for term in selected_terms:
            postings[term].append(i)

    raw_pairs: set[tuple[int, int]] = set()
    for ids in postings.values():
        if len(ids) < 2:
            continue
        for a_pos, a in enumerate(ids[:-1]):
            for b in ids[a_pos + 1:]:
                raw_pairs.add((a, b))

    scored: list[dict[str, Any]] = []
    for i, j in raw_pairs:
        left, right = events[i], events[j]
        left_role = left.get("source_role")
        right_role = right.get("source_role")
        left_miller = left_role == "miller_intervention"
        right_miller = right_role == "miller_intervention"
        if not (left_miller or right_miller):
            continue
        left_date, right_date = _event_date(left), _event_date(right)
        if left_date is None or right_date is None:
            continue
        left_body, right_body = left.get("body"), right.get("body")
        same_body = bool(left_body and right_body and left_body == right_body)
        if not same_body and not allow_cross_body:
            continue
        common_terms = vectors[i].keys() & vectors[j].keys()
        # Use all event terms for the reviewer-visible overlap, but score only
        # terms retained in the bounded high-IDF vectors.
        event_common = term_counts[i].keys() & term_counts[j].keys()
        later_explicit = False
        relation: str | None = None
        earlier, later = left, right
        earlier_date, later_date = left_date, right_date

        # Same-date cross-source match is useful for finding the full meeting
        # transcript near a cue, but it is not a chronological comparison.
        same_date = left_date == right_date
        if same_date:
            left_source_type = left.get("source_type")
            right_source_type = right.get("source_type")
            source_pair = {left_source_type, right_source_type}
            if source_pair == {"caption_aligned_intervention_index", "caption_transcript_database"}:
                relation = "same_meeting_source_crosscheck"
                if not same_body:
                    continue
                # Not necessarily independent corroboration: both may derive
                # from caption tracks for the same video.
            else:
                # Same-day records have no reliable order unless the aligned
                # cue source provides an explicit video timestamp.
                if left_miller and right.get("source_role") == "meeting_context_cue" and _event_video(left) and _event_video(left) == _event_video(right):
                    # Only a context cue after the Miller cue is a sequence lead.
                    if float(right.get("source", {}).get("t0") or 0) > float(left.get("source", {}).get("t1") or 0):
                        earlier, later = left, right
                        relation = "same_meeting_sequence_candidate"
                    else:
                        continue
                elif right_miller and left.get("source_role") == "meeting_context_cue" and _event_video(right) and _event_video(left) == _event_video(right):
                    if float(left.get("source", {}).get("t0") or 0) > float(right.get("source", {}).get("t1") or 0):
                        earlier, later = right, left
                        relation = "same_meeting_sequence_candidate"
                    else:
                        continue
                else:
                    continue
        else:
            if left_date < right_date:
                earlier, later = left, right
                earlier_date, later_date = left_date, right_date
            else:
                earlier, later = right, left
                earlier_date, later_date = right_date, left_date
            gap = (later_date - earlier_date).days
            if gap <= 0 or gap > max_date_gap_days:
                continue
            relation = "cross_meeting_chronology_candidate"
            later_explicit = "cross_meeting_chronology" in (later.get("tactic_candidates") or [])

        left_tactics = set(left.get("tactic_candidates") or [])
        right_tactics = set(right.get("tactic_candidates") or [])
        if relation == "cross_meeting_chronology_candidate":
            # Avoid promoting a later roll call, agenda boilerplate, or generic
            # action marker into an issue chronology link by vocabulary alone.
            if not left_tactics or not right_tactics:
                continue
        else:
            # Same-meeting checks must be anchored by an actual tactic-pattern
            # match in the Miller cue; the other source may supply context only.
            miller_tactics = left_tactics if left_miller else right_tactics
            if not miller_tactics:
                continue

        # Explicit chronology language lowers the issue-token bar, but does
        # not eliminate the required shared-topic check. Cross-meeting links
        # without that marker need at least three shared issue terms.
        if later_explicit:
            min_terms = 1
        elif relation == "cross_meeting_chronology_candidate":
            min_terms = max(min_shared_terms, 3)
        else:
            min_terms = max(min_shared_terms, 2)
        if len(event_common) < min_terms or not common_terms:
            continue
        similarity = _cosine(vectors[i], vectors[j], idf)
        if similarity < min_similarity:
            continue
        tactic_overlap = sorted(set(left.get("tactic_candidates", [])) & set(right.get("tactic_candidates", [])))
        rank_score = similarity + (0.06 if later_explicit else 0.0) + (0.02 if tactic_overlap else 0.0)
        shared_ranked = sorted(event_common, key=lambda term: (idf.get(term, 0.0), term), reverse=True)[:12]
        if relation == "same_meeting_source_crosscheck":
            # Keep the Miller cue first and the meeting-level text second, but
            # do not call either source temporally earlier/later.
            record_a = left if left_miller else right
            record_b = right if left_miller else left
            temporal_earlier = temporal_later = None
        else:
            record_a, record_b = earlier, later
            temporal_earlier, temporal_later = earlier, later
        if relation == "same_meeting_sequence_candidate":
            time_gap_seconds = round(float(later.get("source", {}).get("t0") or 0) - float(earlier.get("source", {}).get("t1") or 0), 1)
        else:
            time_gap_seconds = None
        pair_id = hashlib.sha256(f"{record_a['event_id']}|{record_b['event_id']}|{relation}".encode()).hexdigest()[:20]
        miller_anchors = sorted({
            event["event_id"] for event in (record_a, record_b)
            if event.get("source_role") == "miller_intervention"
        })
        scored.append({
            "comparison_id": f"cmp-{pair_id}",
            "relation_kind": relation,
            "record_a_event_id": record_a["event_id"],
            "record_b_event_id": record_b["event_id"],
            "record_a_source_id": record_a.get("source", {}).get("source_id"),
            "record_b_source_id": record_b.get("source", {}).get("source_id"),
            "record_a_date": record_a.get("date"),
            "record_b_date": record_b.get("date"),
            "record_a_role": record_a.get("source_role"),
            "record_b_role": record_b.get("source_role"),
            "earlier_event_id": temporal_earlier["event_id"] if temporal_earlier else None,
            "later_event_id": temporal_later["event_id"] if temporal_later else None,
            "earlier_source_id": temporal_earlier.get("source", {}).get("source_id") if temporal_earlier else None,
            "later_source_id": temporal_later.get("source", {}).get("source_id") if temporal_later else None,
            "earlier_date": temporal_earlier.get("date") if temporal_earlier else None,
            "later_date": temporal_later.get("date") if temporal_later else None,
            "chronological_order_available": relation != "same_meeting_source_crosscheck",
            "miller_anchor_event_ids": miller_anchors,
            "date_gap_days": ((later_date - earlier_date).days if not same_date else 0),
            "same_body": same_body,
            "same_video": bool(_event_video(record_a) and _event_video(record_a) == _event_video(record_b)),
            "same_meeting_sequence_gap_seconds": time_gap_seconds,
            "same_meeting_source_crosscheck_is_independent_corroboration": (
                "not established; both records may derive from the same caption source"
                if relation == "same_meeting_source_crosscheck" else None
            ),
            "shared_issue_terms": shared_ranked,
            "shared_tactic_candidates": tactic_overlap,
            "later_explicit_chronology_marker": later_explicit,
            "lexical_cosine_similarity": round(similarity, 6),
            "candidate_rank_score": round(rank_score, 6),
            "rank_score_is_probability_or_confidence": False,
            "candidate_basis": [
                "source-linked phrase candidates",
                "shared issue vocabulary",
                "tactic-pattern candidates on both sides" if relation == "cross_meeting_chronology_candidate" else "Miller cue has a tactic-pattern candidate",
                "chronology by date" if relation == "cross_meeting_chronology_candidate" else "same-meeting source/timing link",
                "same body" if same_body else "cross-body match explicitly enabled",
                "later chronology phrase lowers term threshold" if later_explicit else "minimum shared-term threshold applied",
            ],
            "candidate_status": "ranked comparison lead; not a contradiction, admission, causal finding, or legal conclusion",
            "review": _review_fields(relation),
        })

    # Return only the top N pair leads per Miller anchor; not a globally
    # chosen "best contradiction." Each pair is retained if selected for either anchor.
    by_anchor: dict[str, list[dict[str, Any]]] = collections.defaultdict(list)
    for pair in scored:
        for event_id in pair.get("miller_anchor_event_ids", []):
            by_anchor[event_id].append(pair)
    keep_ids: set[str] = set()
    for candidates in by_anchor.values():
        candidates.sort(key=lambda p: (
            -p["candidate_rank_score"], -p["lexical_cosine_similarity"],
            p["date_gap_days"], p["comparison_id"],
        ))
        keep_ids.update(p["comparison_id"] for p in candidates[:top_per_miller_event])
    selected = [p for p in scored if p["comparison_id"] in keep_ids]
    return sorted(selected, key=lambda p: (
        p["relation_kind"], -p["candidate_rank_score"], p.get("earlier_date") or p.get("record_a_date") or "",
        p.get("later_date") or p.get("record_b_date") or "", p["comparison_id"],
    ))


def build_report(
    interventions_path: str | Path,
    meetings_db_path: str | Path | None = DEFAULT_MEETINGS_DB,
    min_alignment_score: float = 0.80,
    include_context: bool = True,
    min_shared_terms: int = 2,
    min_similarity: float = 0.08,
    top_per_miller_event: int = 3,
    max_date_gap_days: int = 3650,
    allow_cross_body: bool = False,
) -> dict[str, Any]:
    intervention_records, intervention_stats = load_intervention_records(
        interventions_path, min_alignment_score=min_alignment_score, include_context=include_context,
    )
    meeting_records: list[dict[str, Any]] = []
    meeting_stats: dict[str, Any] | None = None
    if meetings_db_path is not None:
        meeting_records, meeting_stats = load_meeting_context(meetings_db_path)

    all_records = intervention_records + meeting_records
    events = extract_events(all_records)
    comparisons = rank_comparison_candidates(
        events,
        min_shared_terms=min_shared_terms,
        min_similarity=min_similarity,
        top_per_miller_event=top_per_miller_event,
        max_date_gap_days=max_date_gap_days,
        allow_cross_body=allow_cross_body,
    )
    by_tactic: collections.Counter[str] = collections.Counter()
    by_role: collections.Counter[str] = collections.Counter()
    for event in events:
        by_role[str(event.get("source_role") or "unknown")] += 1
        by_tactic.update(event.get("tactic_candidates") or [])
    relations = collections.Counter(p["relation_kind"] for p in comparisons)
    metadata = {
        "schema_version": SCHEMA_VERSION,
        "algorithm_version": ALGORITHM_VERSION,
        "generated_at_utc": dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(),
        "inputs": {
            "interventions": {
                "path": str(interventions_path),
                "sha256": sha256_file(interventions_path),
                **intervention_stats,
            },
            "meeting_context": (
                {
                    "path": str(meetings_db_path),
                    "sha256": sha256_file(meetings_db_path),
                    **(meeting_stats or {}),
                } if meetings_db_path is not None else {"included": False}
            ),
        },
        "processing_policy": {
            "source_texts_modified": False,
            "speaker_assignment_inferred": False,
            "tactic_labels_are_candidates_only": True,
            "contradictions_auto_determined": False,
            "causation_auto_determined": False,
            "estoppel_or_immunity_auto_determined": False,
            "rank_score_is_calibrated_confidence": False,
        },
        "thresholds": {
            "min_alignment_score": min_alignment_score,
            "min_shared_issue_terms": min_shared_terms,
            "min_tfidf_cosine": min_similarity,
            "top_pairs_per_miller_event": top_per_miller_event,
            "max_cross_meeting_gap_days": max_date_gap_days,
            "allow_cross_body": allow_cross_body,
        },
    }
    return {
        "metadata": metadata,
        "summary": {
            "source_records": len(all_records),
            "events": len(events),
            "events_by_source_role": dict(sorted(by_role.items())),
            "candidate_signal_counts": dict(sorted(by_tactic.items())),
            "comparison_candidates": len(comparisons),
            "comparison_candidates_by_relation": dict(sorted(relations.items())),
            "interpretation": "Counts are pattern matches and ranked leads, not verified events, contradictions, legal findings, or causal effects.",
        },
        "events": events,
        "comparison_candidates": comparisons,
    }


def write_review_csv(report: dict[str, Any], path: str | Path) -> None:
    """Write a compact analyst queue; full evidence and statuses remain in JSON."""
    event_map = {event["event_id"]: event for event in report.get("events", [])}
    fields = [
        "comparison_id", "relation_kind", "chronological_order_available",
        "record_a_date", "record_a_role", "record_a_title", "record_a_url", "record_a_excerpt", "record_a_tactics",
        "record_b_date", "record_b_role", "record_b_title", "record_b_url", "record_b_excerpt", "record_b_tactics",
        "shared_issue_terms", "shared_tactic_candidates", "lexical_cosine_similarity", "candidate_rank_score",
        "review_status", "same_issue", "same_proposition", "same_scope_and_stage",
        "same_authority_or_speaker", "material_facts_changed", "response_or_cure", "contradiction",
        "causal_link", "legal_effect",
    ]
    with Path(path).open("w", encoding="utf-8-sig", newline="") as stream:
        writer = csv.DictWriter(stream, fieldnames=fields)
        writer.writeheader()
        for pair in report.get("comparison_candidates", []):
            record_a = event_map[pair["record_a_event_id"]]
            record_b = event_map[pair["record_b_event_id"]]
            source_a, source_b = record_a.get("source", {}), record_b.get("source", {})
            review = pair.get("review", {})
            writer.writerow({
                "comparison_id": pair["comparison_id"],
                "relation_kind": pair["relation_kind"],
                "chronological_order_available": pair.get("chronological_order_available"),
                "record_a_date": record_a.get("date"),
                "record_a_role": record_a.get("source_role"),
                "record_a_title": record_a.get("title"),
                "record_a_url": source_a.get("source_url"),
                "record_a_excerpt": record_a.get("evidence_excerpt"),
                "record_a_tactics": ";".join(record_a.get("tactic_candidates", [])),
                "record_b_date": record_b.get("date"),
                "record_b_role": record_b.get("source_role"),
                "record_b_title": record_b.get("title"),
                "record_b_url": source_b.get("source_url"),
                "record_b_excerpt": record_b.get("evidence_excerpt"),
                "record_b_tactics": ";".join(record_b.get("tactic_candidates", [])),
                "shared_issue_terms": ";".join(pair.get("shared_issue_terms", [])),
                "shared_tactic_candidates": ";".join(pair.get("shared_tactic_candidates", [])),
                "lexical_cosine_similarity": pair.get("lexical_cosine_similarity"),
                "candidate_rank_score": pair.get("candidate_rank_score"),
                "review_status": review.get("review_status"),
                "same_issue": review.get("same_issue"),
                "same_proposition": review.get("same_proposition"),
                "same_scope_and_stage": review.get("same_scope_and_stage"),
                "same_authority_or_speaker": review.get("same_authority_or_speaker"),
                "material_facts_changed": review.get("material_facts_changed"),
                "response_or_cure": review.get("response_or_cure"),
                "contradiction": review.get("contradiction"),
                "causal_link": review.get("causal_link"),
                "legal_effect": review.get("legal_effect"),
            })


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--interventions", default=DEFAULT_INTERVENTIONS, help="caption-aligned Miller intervention JSON")
    parser.add_argument("--meetings-db", default=DEFAULT_MEETINGS_DB, help="meeting-level caption DB (.json or .json.gz); use --no-meetings-db to disable")
    parser.add_argument("--no-meetings-db", action="store_true", help="run only on the intervention index")
    parser.add_argument("--out", required=True, help="path to JSON audit output (choose /tmp or another ignored location)")
    parser.add_argument("--review-csv", help="optional compact human-review queue CSV")
    parser.add_argument("--min-alignment-score", type=float, default=0.80)
    parser.add_argument("--no-context", action="store_true", help="omit context/interruption cue blocks")
    parser.add_argument("--min-shared-terms", type=int, default=2)
    parser.add_argument("--min-similarity", type=float, default=0.08)
    parser.add_argument("--top-per-miller-event", type=int, default=3)
    parser.add_argument("--max-date-gap-days", type=int, default=3650)
    parser.add_argument("--allow-cross-body", action="store_true", help="allow cross-body leads; default requires same normalized body")
    args = parser.parse_args(argv)

    for name, value in (("min-alignment-score", args.min_alignment_score), ("min-similarity", args.min_similarity)):
        if not 0 <= value <= 1:
            parser.error(f"--{name} must be between 0 and 1")
    if args.min_shared_terms < 1 or args.top_per_miller_event < 1 or args.max_date_gap_days < 1:
        parser.error("term count, per-event cap, and date gap must be positive")
    if not Path(args.interventions).is_file():
        parser.error(f"interventions file does not exist: {args.interventions}")
    db_path: str | None = None if args.no_meetings_db else args.meetings_db
    if db_path is not None and not Path(db_path).is_file():
        parser.error(f"meeting database does not exist: {db_path} (or pass --no-meetings-db)")

    report = build_report(
        interventions_path=args.interventions,
        meetings_db_path=db_path,
        min_alignment_score=args.min_alignment_score,
        include_context=not args.no_context,
        min_shared_terms=args.min_shared_terms,
        min_similarity=args.min_similarity,
        top_per_miller_event=args.top_per_miller_event,
        max_date_gap_days=args.max_date_gap_days,
        allow_cross_body=args.allow_cross_body,
    )
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.review_csv:
        review_path = Path(args.review_csv)
        review_path.parent.mkdir(parents=True, exist_ok=True)
        write_review_csv(report, review_path)
    print(json.dumps(report["summary"], ensure_ascii=False, indent=2))
    print(f"wrote JSON report: {out}")
    if args.review_csv:
        print(f"wrote analyst queue: {args.review_csv}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
