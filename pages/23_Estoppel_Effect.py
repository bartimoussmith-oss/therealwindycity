"""Public, cached research queue for source-linked estoppel-effect candidates.

The algorithm runs when this page is opened, then caches results against the
input-file hashes. It never makes legal or factual determinations.
"""
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

st.set_page_config(page_title="Estoppel-Effect Review", page_icon="⚖️", layout="wide")

from tools.estoppel_effect import build_report, sha256_file, write_review_csv  # noqa: E402

INTERVENTIONS = ROOT / "pipeline" / "miller_interventions.json"
MEETINGS_DB = ROOT / "drive-import" / "master_meetings_database.json.gz"


@st.cache_resource(show_spinner=False, max_entries=1)
def _cached_report(
    interventions_path: str,
    meetings_db_path: str | None,
    interventions_sha256: str,
    meetings_db_sha256: str | None,
) -> dict:
    """Cache one read-only corpus result; content hashes invalidate on data changes."""
    return build_report(
        interventions_path=interventions_path,
        meetings_db_path=meetings_db_path,
    )


@st.cache_data(show_spinner=False, max_entries=1)
def _json_download(
    interventions_path: str,
    meetings_db_path: str | None,
    interventions_sha256: str,
    meetings_db_sha256: str | None,
) -> bytes:
    report = _cached_report(
        interventions_path, meetings_db_path, interventions_sha256, meetings_db_sha256,
    )
    return (json.dumps(report, ensure_ascii=False, indent=2) + "\n").encode("utf-8")


@st.cache_data(show_spinner=False, max_entries=1)
def _csv_download(
    interventions_path: str,
    meetings_db_path: str | None,
    interventions_sha256: str,
    meetings_db_sha256: str | None,
) -> bytes:
    report = _cached_report(
        interventions_path, meetings_db_path, interventions_sha256, meetings_db_sha256,
    )
    with tempfile.TemporaryDirectory(prefix="estoppel-effect-") as temp_dir:
        path = Path(temp_dir) / "estoppel-effect-review.csv"
        write_review_csv(report, path)
        return path.read_bytes()


def _source_caption(event: dict) -> str:
    source = event.get("source", {})
    parts = [f"Source ID: `{source.get('source_id') or 'unknown'}`"]
    if source.get("alignment_score") is not None:
        parts.append(f"alignment score {source['alignment_score']:.2f} (not a probability)")
    if source.get("t0") is not None:
        parts.append(f"cue {source['t0']}–{source.get('t1')} sec")
    digest = event.get("source_text_sha256")
    if digest:
        parts.append(f"text SHA-256 `{digest[:16]}…`")
    return " · ".join(parts)


def _comparison_row(pair: dict, event_map: dict[str, dict]) -> dict:
    record_a = event_map[pair["record_a_event_id"]]
    record_b = event_map[pair["record_b_event_id"]]
    return {
        "Relation": pair["relation_kind"],
        "Date A": record_a.get("date") or "Unknown",
        "Date B": record_b.get("date") or "Unknown",
        "Record A": record_a.get("title") or "Untitled source",
        "Record B": record_b.get("title") or "Untitled source",
        "Shared issue terms": ", ".join(pair.get("shared_issue_terms", [])),
        "Tactic-pattern overlap": ", ".join(pair.get("shared_tactic_candidates", [])),
        "Lexical similarity": pair.get("lexical_cosine_similarity"),
        "Review": pair.get("review", {}).get("review_status", "unreviewed"),
    }


def _render_event(label: str, event: dict, key: str) -> None:
    source = event.get("source", {})
    st.markdown(f"**{label}: {event.get('date') or 'Unknown date'} · {event.get('source_role') or 'unknown role'}**")
    st.caption(event.get("title") or "Untitled source")
    st.caption(_source_caption(event))
    if source.get("source_url"):
        st.link_button("Open source video at cue", source["source_url"], key=key)
    else:
        st.caption("No direct source URL is stored for this meeting-level excerpt.")
    st.code(event.get("evidence_excerpt") or "[No excerpt stored]")
    attribution = event.get("speaker_attribution") or "Not assigned"
    st.caption(f"Attribution: {attribution}")
    st.caption(
        "Pattern tags: " + (", ".join(event.get("tactic_candidates", [])) or "none")
        + (" · Diagnostics: " + ", ".join(event.get("diagnostic_markers", []))
           if event.get("diagnostic_markers") else "")
    )


def _render_candidate(pair: dict, event_map: dict[str, dict]) -> None:
    record_a = event_map[pair["record_a_event_id"]]
    record_b = event_map[pair["record_b_event_id"]]
    terms = ", ".join(pair.get("shared_issue_terms", [])) or "no shared terms listed"
    heading = (
        f"{record_a.get('date') or 'Unknown'} ↔ {record_b.get('date') or 'Unknown'}"
        f" · {pair['relation_kind']} · {terms[:110]}"
    )
    with st.expander(heading):
        st.caption(
            f"Lexical cosine: {pair['lexical_cosine_similarity']:.3f} · "
            f"rank score: {pair['candidate_rank_score']:.3f} (not confidence or probability)"
        )
        st.caption(pair.get("candidate_status", "Unreviewed candidate"))
        if pair["relation_kind"] == "same_meeting_source_crosscheck":
            st.info(
                "This is a same-date source cross-check, not a chronological pair. "
                "Independent corroboration is not established; both texts may derive from the same captions."
            )
        elif pair["relation_kind"] == "same_meeting_sequence_candidate":
            st.info(
                "Timestamp order places the context cue after the Miller-labelled cue; "
                "that does not prove response, reliance, or cure."
            )
        else:
            st.info(
                "Dates order these candidate records only. Confirm the original source, "
                "same proposition, authority, stage, and intervening facts."
            )

        col_a, col_b = st.columns(2)
        with col_a:
            _render_event("Record A", record_a, f"{pair['comparison_id']}-a")
        with col_b:
            _render_event("Record B", record_b, f"{pair['comparison_id']}-b")

        review = pair.get("review", {})
        st.markdown("**Human review remains unassessed**")
        st.write({
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


# ----------------------------------------------------------------------- page
st.title("⚖️ Estoppel-Effect Research Queue")
st.warning(
    "This page automatically runs the phrase-match research aid against the "
    "available local transcript inputs and caches the result by input-file hash. "
    "It does not determine legal effect."
)
st.markdown(
    "**A recorded objection is not automatically actual notice, a violation, or estoppel.** "
    "Speaker attribution, contradiction, reliance, prejudice, causation, authority, "
    "and legal effect remain for human review."
)

if not INTERVENTIONS.is_file():
    st.error(f"Required intervention index is missing: `{INTERVENTIONS.relative_to(ROOT)}`")
    st.stop()
if not MEETINGS_DB.is_file():
    st.error(f"Required meeting transcript database is missing: `{MEETINGS_DB.relative_to(ROOT)}`")
    st.stop()

include_context = st.checkbox(
    "Include unattributed meeting-level transcript context",
    value=True,
    help="Context excerpts are not assigned to speakers. Turn off for cue-index-only results.",
)
interventions_hash = sha256_file(INTERVENTIONS)
meetings_hash = sha256_file(MEETINGS_DB) if include_context else None
meetings_path = str(MEETINGS_DB) if include_context else None
cache_args = (
    str(INTERVENTIONS), meetings_path, interventions_hash, meetings_hash,
)

if st.button("Rebuild analysis now", help="Clear this page's cached report and rerun the inputs."):
    _cached_report.clear()
    _json_download.clear()
    _csv_download.clear()
    st.rerun()

with st.spinner("Running the first analysis can take around 40 seconds; the result is cached afterward…"):
    try:
        report = _cached_report(*cache_args)
    except Exception as exc:
        st.error(f"The analysis could not be built: {type(exc).__name__}: {exc}")
        st.stop()

summary = report["summary"]
metadata = report["metadata"]
by_relation = summary.get("comparison_candidates_by_relation", {})
metric_cols = st.columns(4)
metric_cols[0].metric("Source records", summary.get("source_records", 0))
metric_cols[1].metric("Phrase-event clusters", summary.get("events", 0))
metric_cols[2].metric("Cross-meeting leads", by_relation.get("cross_meeting_chronology_candidate", 0))
metric_cols[3].metric("All comparison leads", summary.get("comparison_candidates", 0))

st.caption(
    f"Generated {metadata.get('generated_at_utc', 'unknown')} · "
    f"algorithm {metadata.get('algorithm_version', 'unknown')} · "
    f"meeting context {'included' if include_context else 'omitted'} · "
    f"{summary.get('interpretation', '')}"
)

with st.expander("Download this run"):
    json_bytes = _json_download(*cache_args)
    csv_bytes = _csv_download(*cache_args)
    dcol_a, dcol_b = st.columns(2)
    dcol_a.download_button(
        "Download full JSON audit",
        data=json_bytes,
        file_name="estoppel-effect-audit.json",
        mime="application/json",
        key="estoppel-effect-json-download",
    )
    dcol_b.download_button(
        "Download analyst CSV queue",
        data=csv_bytes,
        file_name="estoppel-effect-review.csv",
        mime="text/csv",
        key="estoppel-effect-csv-download",
    )

queue_tab, signals_tab, limits_tab = st.tabs(["Comparison queue", "Phrase signals", "Method and limits"])
with queue_tab:
    candidates = report.get("comparison_candidates", [])
    event_map = {event["event_id"]: event for event in report.get("events", [])}
    relation_values = sorted({pair["relation_kind"] for pair in candidates})
    filters = st.columns([2, 3, 1])
    relation_filter = filters[0].selectbox("Relation", ["All"] + relation_values)
    search_filter = filters[1].text_input("Search titles, excerpts, or shared terms")
    limit = filters[2].selectbox("Show", [25, 50, 100, 200, 500], index=1)

    filtered = [
        pair for pair in candidates
        if relation_filter == "All" or pair["relation_kind"] == relation_filter
    ]
    if search_filter.strip():
        query = search_filter.casefold()
        filtered = [
            pair for pair in filtered
            if query in " ".join([
                " ".join(pair.get("shared_issue_terms", [])),
                event_map[pair["record_a_event_id"]].get("title") or "",
                event_map[pair["record_a_event_id"]].get("evidence_excerpt") or "",
                event_map[pair["record_b_event_id"]].get("title") or "",
                event_map[pair["record_b_event_id"]].get("evidence_excerpt") or "",
            ]).casefold()
        ]
    filtered.sort(key=lambda pair: (-pair["candidate_rank_score"], pair["comparison_id"]))
    st.caption(f"Showing {min(len(filtered), limit)} of {len(filtered)} matching, unreviewed leads.")
    if filtered:
        st.dataframe(
            [_comparison_row(pair, event_map) for pair in filtered[:limit]],
            hide_index=True,
            width="stretch",
        )
        for pair in filtered[:limit]:
            _render_candidate(pair, event_map)
    else:
        st.info("No candidates match these filters. That is not a finding about the underlying record.")

with signals_tab:
    st.markdown("Signal counts are phrase/event matches, not unique verified statements or speakers.")
    st.dataframe(
        [
            {"Signal tag": tag, "Candidate matches": count}
            for tag, count in summary.get("candidate_signal_counts", {}).items()
        ],
        hide_index=True,
        width="stretch",
    )
    st.dataframe(
        [
            {"Source role": role, "Phrase-event clusters": count}
            for role, count in summary.get("events_by_source_role", {}).items()
        ],
        hide_index=True,
        width="stretch",
    )

with limits_tab:
    st.markdown(
        """
### What the score means
The queue ranks lexical overlap and source/date relationships. The score is not a
probability, confidence value, legal-strength rating, or finding. Cross-meeting
links require tactic-pattern candidates on both sides, normalized issue-term
overlap, same-body matching by default, and dates within the configured range.

### Source limitations
The Miller cue label comes from the intervention compilation and is not
independently audio-verified. The meeting-level source is unattributed per
excerpt; a meeting JSON with one `turns` entry does not establish speaker-level
attribution. A same-meeting source cross-check may reuse the same caption source
and is not independent corroboration by itself. Excerpts can cross speaker
boundaries, include transcription errors, or omit material context.

### Human review required
Open original video/minutes; verify exact wording and attribution; compare the
same issue and proposition, scope, stage, and authority; inspect changed facts,
responses, adopted text, and outcomes; and assess notice, reliance, prejudice,
causation, and governing law separately. Never infer estoppel from an objection,
phrase match, sequence, or silence alone.
"""
    )
    st.caption("Full algorithm/runbook: `tools/ESTOPPEL_EFFECT_ALGORITHM.md` in the repository.")

st.divider()
st.caption(
    "Research aid only · no legal conclusions · source inputs are read-only · "
    "refreshing is local to this app's cached report."
)
