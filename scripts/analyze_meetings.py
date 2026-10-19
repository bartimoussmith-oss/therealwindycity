#!/usr/bin/env python3
"""Build a conservative, source-linked pre-meeting screen from local agenda files.

This tool does not fetch URLs, bypass robots.txt, or make legal findings. It
extracts numbered agenda rows from local HTML/text/PDF files and produces
candidate review lanes plus an evidence checklist. Agenda text alone cannot
establish what happened at a meeting, who spoke, how a rule was applied, or
whether any legal element is met.

Example:
    python3 scripts/analyze_meetings.py \
        --input pipeline/docs/1124/2026-08-10_agenda.html \
        --source-url 'https://cheyenne.granicus.com/GeneratedAgendaViewer.php?view_id=5&event_id=1124' \
        --out output/municipal_analysis_report.json

The URL is provenance metadata only; this program never requests it. For a
new automated feed, use an authorized and robots-permitted source or provide a
locally exported agenda file.
"""

from __future__ import annotations

import argparse
import hashlib
import html
from html.parser import HTMLParser
import json
import re
import sys
from dataclasses import dataclass
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence
from urllib.parse import urlparse

SCHEMA_VERSION = "ivic-agenda-screen/1.0"
SUPPORTED_SUFFIXES = {".html", ".htm", ".txt", ".md", ".pdf"}

# Topic tags are retrieval cues, not legal conclusions. Keep terms explicit and
# preserve the matching words in the report so a reviewer can assess context.
TOPIC_CUES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "land_use_annexation_zoning",
        (
            "annex", "zoning", "zoning map", "subdivision", "plat",
            "site plan", "land use", "variance", "rezon", "development plan",
        ),
    ),
    (
        "procurement_contract",
        (
            "bid", "contract", "agreement", "purchase order", "request for proposal",
            "request for proposals", "r.f.p.", "procurement", "maintenance service",
            "professional services",
        ),
    ),
    (
        "property_funding_or_spending",
        (
            "property", "lease", "purchase", "donation", "grant", "appropriation",
            "funding", "reimbursement", "tax", "not to exceed",
        ),
    ),
    (
        "public_hearing_or_comment",
        ("public hearing", "hearing", "public comment", "speaker", "comment period"),
    ),
    (
        "inspection_or_enforcement",
        (
            "inspection", "inspect", "search warrant", "warrant", "code enforcement",
            "right of entry", "compliance inspection",
        ),
    ),
    (
        "remote_access_or_accommodation",
        (
            "remote", "zoom", "hybrid", "caption", "accessibility", "accommodation",
            "teleconference", "videoconference",
        ),
    ),
    (
        "speech_rule_or_meeting_procedure",
        (
            "rules of procedure", "public comment", "time limit", "speaker", "speaking",
            "public participation", "agenda order",
        ),
    ),
)

PATHWAY_NOTES: tuple[tuple[str, str], ...] = (
    (
        "speech_forum_access",
        "Agenda text does not show the forum's purpose or rule, the speaker's role and topic, recognition, stated reason, comparable treatment, invitation to answer, charged time, or an actual lost opportunity.",
    ),
    (
        "retaliation",
        "Agenda text does not establish protected expression, a later adverse act, the actor's knowledge, causation, or an actionable injury. An adverse vote is not automatically retaliation.",
    ),
    (
        "federal_procedural_due_process",
        "Agenda text does not identify a claimant's protected property or liberty interest, a deprivation, or the process due. Policy disagreement and a parcel-specific agenda item do not alone establish an interest or quasi-judicial status.",
    ),
    (
        "takings_and_property",
        "Agenda text does not establish the claimant's relevant property interest, government interference, finality, concrete impact, or requested relief. Annexation, neighboring development, or a policy disagreement is not automatically a taking.",
    ),
    (
        "search_inspection_and_entry",
        "Distinguish a proposal, adopted authority, demand, warrant, entry, and actual search. Agenda text does not establish that any occurred; do not assume every administrative warrant requires known individualized criminal wrongdoing or owner attendance.",
    ),
    (
        "equal_protection",
        "Agenda text does not establish a protected-class status, government classification, comparator, or intentional unequal treatment. No status or intent is inferred.",
    ),
    (
        "accessibility_ada_title_ii",
        "Agenda text does not establish disability, an accommodation request, a disability-related communication barrier, or denial of effective communication. No disability or universal platform entitlement is inferred.",
    ),
    (
        "wyoming_state_local_procedure",
        "Agenda text alone does not establish a statutory or local-rule violation. Keep Wyoming constitutional/statutory, open-meetings, local procedural, and federal lanes distinct.",
    ),
    (
        "non_legal_policy_or_discourtesy",
        "Agenda text alone does not show how participants were treated. Any later policy or discourtesy observation must be supported by meeting evidence and kept separate from legal claims.",
    ),
)

PATHWAY_CUE_MAP = {
    "speech_forum_access": {"public_hearing_or_comment", "speech_rule_or_meeting_procedure"},
    "retaliation": set(),
    "federal_procedural_due_process": {"land_use_annexation_zoning", "property_funding_or_spending"},
    "takings_and_property": {"land_use_annexation_zoning", "property_funding_or_spending"},
    "search_inspection_and_entry": {"inspection_or_enforcement"},
    "equal_protection": set(),
    "accessibility_ada_title_ii": {"remote_access_or_accommodation"},
    "wyoming_state_local_procedure": {"public_hearing_or_comment", "speech_rule_or_meeting_procedure"},
    "non_legal_policy_or_discourtesy": set(),
}

REQUIRED_COMPARATOR_FIELDS = [
    "same meeting and agenda item",
    "speaker role and topic",
    "rule version and forum purpose",
    "recognition and time remaining",
    "invitation to answer and actual lost opportunity",
    "conduct and stated reason",
    "elapsed time, pauses, technical delay, and charged speaking time",
    "outcome and repeated-speaker clustering",
]

MONTHS = (
    "January February March April May June July August September October November December"
).split()
MONTH_PATTERN = "|".join(MONTHS)
DATE_RE = re.compile(rf"\b({MONTH_PATTERN})\s+(\d{{1,2}}),?\s+(\d{{4}})\b", re.I)
ISO_DATE_RE = re.compile(r"\b(20\d{2})-(\d{2})-(\d{2})\b")


@dataclass
class AgendaItem:
    item_number: str | None
    parent_item_number: str | None
    title: str
    action: str
    item_type: str
    consent_agenda: bool
    committees: list[str]
    extraction_method: str
    source_position: int

    def to_dict(self, source: dict[str, object]) -> dict[str, object]:
        full_text = " ".join(part for part in (self.title, self.action) if part).strip()
        topic_cues = detect_topic_cues(full_text)
        cue_names = {str(cue["topic"]) for cue in topic_cues}
        pathways = {
            lane: {
                "status": "EVIDENCE INCOMPLETE",
                "candidate_review_cue_present": bool(cue_names & PATHWAY_CUE_MAP.get(lane, set())),
                "matched_agenda_topics": sorted(cue_names & PATHWAY_CUE_MAP.get(lane, set())),
                "note": note,
            }
            for lane, note in PATHWAY_NOTES
        }
        return {
            "item_number": self.item_number,
            "parent_item_number": self.parent_item_number,
            "item_type": self.item_type,
            "title_as_extracted": self.title,
            "action_as_extracted": self.action or None,
            "consent_agenda_marker_present": self.consent_agenda,
            "committee_text_as_extracted": self.committees,
            "extraction_method": self.extraction_method,
            "source_position": self.source_position,
            "source_position_basis": (
                "parsed_html_table_row_ordinal"
                if self.extraction_method == "html_table_row"
                else "local_text_line_number"
            ),
            "status": "SOURCE LEAD",
            "source": source,
            "topic_cues": topic_cues,
            "framework_screen": pathways,
            "comparator_review": {
                "status": "EVIDENCE INCOMPLETE",
                "note": "No speaker turns, rule application, or time records are established by an agenda. Do not label similar agenda titles as comparators.",
                "required_matching_fields": REQUIRED_COMPARATOR_FIELDS,
            },
            "open_evidence_tasks": [
                "Verify this is the final agenda and preserve the official packet, linked documents, posting/version history, and any adopted rule text.",
                "For any speech/access review, record the forum purpose and rule version, participant role and topic, recognition, invitation, stated reason, exact turn sequence, and timing method.",
                "After the meeting, obtain complete minutes and available audiovisual/caption records; distinguish elapsed time, pauses, technical delay, and charged speaking time.",
            ],
            "review_note": (
                "Deterministic text cues are search leads only. The script does not assess truth, intent, protected status, liability, or legal merits."
            ),
        }


class AgendaHTMLParser(HTMLParser):
    """Collect visible text and table rows without following any embedded links."""

    SKIP_TAGS = {"script", "style", "noscript"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.rows: list[list[str]] = []
        self.document_text: list[str] = []
        self._row: list[str] | None = None
        self._cell: list[str] | None = None
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "tr":
            if self._row is not None:
                self._finish_row()
            self._row = []
            self._cell = None
        elif tag in {"td", "th"} and self._row is not None:
            self._finish_cell()
            self._cell = []
        elif tag in {"br", "p", "div", "li", "h1", "h2", "h3", "h4"}:
            self._append_text(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.SKIP_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag in {"td", "th"}:
            self._finish_cell()
        elif tag == "tr":
            self._finish_row()
        elif tag in {"p", "div", "li", "h1", "h2", "h3", "h4"}:
            self._append_text(" ")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        self.document_text.append(data)
        if self._cell is not None:
            self._cell.append(data)

    def _append_text(self, value: str) -> None:
        if self._skip_depth:
            return
        self.document_text.append(value)
        if self._cell is not None:
            self._cell.append(value)

    def _finish_cell(self) -> None:
        if self._cell is not None:
            assert self._row is not None
            self._row.append(clean_text(" ".join(self._cell)))
            self._cell = None

    def _finish_row(self) -> None:
        if self._row is not None:
            self._finish_cell()
            if any(self._row):
                self.rows.append(self._row)
            self._row = None

    def close(self) -> None:
        super().close()
        self._finish_row()


def clean_text(value: str) -> str:
    value = html.unescape(value).replace("\xa0", " ")
    return re.sub(r"\s+", " ", value).strip()


def detect_topic_cues(text: str) -> list[dict[str, object]]:
    normalized = clean_text(text).casefold()
    matches: list[dict[str, object]] = []
    for label, phrases in TOPIC_CUES:
        found = [phrase for phrase in phrases if phrase.casefold() in normalized]
        if found:
            matches.append({"topic": label, "matched_terms": found})
    return matches


def split_action(text: str) -> tuple[str, str]:
    match = re.search(r"\bACTION\s*:\s*", text, flags=re.I)
    if not match:
        return clean_text(text), ""
    return clean_text(text[:match.start()]), clean_text(text[match.end():])


def classify_item_row(
    cells: Sequence[str], current_parent: str | None, row_number: int, method: str
) -> tuple[AgendaItem | None, str | None, str | None]:
    """Return (item, updated_parent, standalone_action)."""
    nonempty = [clean_text(cell) for cell in cells if clean_text(cell)]
    if not nonempty:
        return None, current_parent, None

    number_match = re.fullmatch(r"(\d{1,3}[A-Za-z]?)[.]?", nonempty[0])
    subitem_match = re.fullmatch(r"([A-Za-z])[.)]", nonempty[0])

    if number_match and len(nonempty) >= 2:
        item_number = number_match.group(1)
        parent = item_number
        description = clean_text(" ".join(nonempty[1:]))
        title, action = split_action(description)
        return make_item(item_number, None, title, action, method, row_number), parent, None

    if subitem_match and len(nonempty) >= 2:
        letter = subitem_match.group(1).lower()
        description = clean_text(" ".join(nonempty[1:]))
        title, action = split_action(description)
        item_number = f"{current_parent}{letter}" if current_parent else letter
        parent = current_parent
        return make_item(item_number, parent, title, action, method, row_number), current_parent, None

    joined = clean_text(" ".join(nonempty))
    action_match = re.match(r"ACTION\s*:\s*(.*)", joined, flags=re.I)
    if action_match:
        return None, current_parent, clean_text(action_match.group(1))
    # Some publisher exports place ACTION after a <br> inside a single cell.
    if re.match(r"^ACTION\s*:", joined, flags=re.I):
        return None, current_parent, clean_text(re.sub(r"^ACTION\s*:\s*", "", joined, flags=re.I))
    return None, current_parent, None


def make_item(
    item_number: str,
    parent_item_number: str | None,
    title: str,
    action: str,
    method: str,
    row_number: int,
) -> AgendaItem:
    consent = bool(re.match(r"^\s*\[\s*CA\s*\]", title, flags=re.I))
    preserved_title = clean_text(title)
    committees = re.findall(r"\(([^()]*\bCOMMITTEE\b[^()]*)\)", preserved_title, flags=re.I)
    item_type = "section" if preserved_title.endswith(":") else "agenda_item"
    return AgendaItem(
        item_number=item_number,
        parent_item_number=parent_item_number,
        title=preserved_title,
        action=action,
        item_type=item_type,
        consent_agenda=consent,
        committees=[clean_text(value) for value in committees],
        extraction_method=method,
        source_position=row_number,
    )


def parse_html_agenda(text: str) -> tuple[list[AgendaItem], str]:
    parser = AgendaHTMLParser()
    parser.feed(text)
    parser.close()
    items: list[AgendaItem] = []
    current_parent: str | None = None
    for row_number, cells in enumerate(parser.rows, start=1):
        item, current_parent, standalone_action = classify_item_row(
            cells, current_parent, row_number, "html_table_row"
        )
        if item is not None:
            items.append(item)
        elif standalone_action and items:
            # Granicus often puts ACTION on a separate colspan row immediately
            # after its item. Attach it only to that preceding extracted row.
            if not items[-1].action:
                items[-1].action = standalone_action
    return items, clean_text(" ".join(parser.document_text))


def parse_plain_agenda(text: str) -> tuple[list[AgendaItem], str]:
    items: list[AgendaItem] = []
    current_parent: str | None = None
    previous: AgendaItem | None = None
    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = clean_text(raw_line)
        if not line:
            continue
        top_match = re.match(r"^(\d{1,3}[A-Za-z]?)[.]\s+(.+)$", line)
        sub_match = re.match(r"^([A-Za-z])[.)]\s+(.+)$", line)
        if top_match:
            item_number, description = top_match.groups()
            current_parent = item_number
            title, action = split_action(description)
            previous = make_item(item_number, None, title, action, "numbered_text_line", line_number)
            items.append(previous)
            continue
        if sub_match:
            letter, description = sub_match.groups()
            title, action = split_action(description)
            item_number = f"{current_parent}{letter.lower()}" if current_parent else letter.lower()
            previous = make_item(item_number, current_parent, title, action, "numbered_text_line", line_number)
            items.append(previous)
            continue
        action_match = re.match(r"^ACTION\s*:\s*(.*)$", line, flags=re.I)
        if action_match and previous is not None and not previous.action:
            previous.action = clean_text(action_match.group(1))
    return items, clean_text(text)


def extract_document_text(path: Path) -> tuple[str, str]:
    suffix = path.suffix.lower()
    if suffix in {".html", ".htm"}:
        return path.read_text(encoding="utf-8", errors="replace"), "html"
    if suffix == ".pdf":
        try:
            from pypdf import PdfReader
        except ImportError as exc:  # pragma: no cover - depends on optional runtime package
            raise RuntimeError("PDF input requires pypdf (available in repository requirements.txt)") from exc
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
        return "\n".join(pages), "text"
    return path.read_text(encoding="utf-8", errors="replace"), "text"


def infer_meeting_date(path: Path, document_text: str) -> str | None:
    # Prefer an ISO date in the agenda file's basename; a file can mention
    # unrelated older dates in individual agenda items.
    iso_match = ISO_DATE_RE.search(path.name)
    if iso_match:
        year, month, day = (int(value) for value in iso_match.groups())
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            pass
    # Meeting date normally appears in the document header, before item rows.
    header = document_text[:2500]
    match = DATE_RE.search(header)
    if match:
        month_name, day_text, year_text = match.groups()
        try:
            return date(int(year_text), MONTHS.index(month_name.title()) + 1, int(day_text)).isoformat()
        except (ValueError, IndexError):
            pass
    return None


def infer_meeting_body(document_text: str, override: str | None = None) -> str | None:
    if override:
        return clean_text(override)
    upper = document_text[:4000].upper()
    candidates = (
        ("City Council", r"\bCITY\s+COUNCIL\b"),
        ("Board of Public Utilities", r"\bBOARD\s+OF\s+PUBLIC\s+UTILITIES\b|\bBOPU\b"),
        ("Laramie County Commission", r"\bLARAMIE\s+COUNTY\s+(?:BOARD\s+OF\s+)?COMMISSION(?:ERS)?\b"),
        ("Planning Commission", r"\bPLANNING\s+COMMISSION\b"),
        ("Board of Adjustment", r"\bBOARD\s+OF\s+ADJUSTMENT\b"),
    )
    for label, pattern in candidates:
        if re.search(pattern, upper):
            return label
    return None


def validate_source_url(value: str | None) -> str | None:
    if not value:
        return None
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("--source-url must be an absolute http(s) URL")
    return value


def build_source_record(path: Path, content: bytes, source_url: str | None) -> dict[str, object]:
    return {
        "local_path": str(path),
        "source_url_as_supplied": source_url,
        "source_url_fetched_by_this_tool": False,
        "sha256": hashlib.sha256(content).hexdigest(),
        "provenance_note": "Local file bytes were hashed. This tool does not independently authenticate the publisher, posting date, or document version.",
    }


def analyze_file(path: Path, source_url: str | None = None, meeting_body: str | None = None) -> dict[str, object]:
    raw_bytes = path.read_bytes()
    raw_text, file_kind = extract_document_text(path)
    source = build_source_record(path, raw_bytes, source_url)

    if file_kind == "html":
        items, document_text = parse_html_agenda(raw_text)
    else:
        items, document_text = parse_plain_agenda(raw_text)

    source["file_kind"] = file_kind
    resolved_body = infer_meeting_body(document_text, meeting_body)
    resolved_date = infer_meeting_date(path, document_text)
    item_records = [item.to_dict(source) for item in items]
    return {
        "meeting_body": resolved_body,
        "meeting_date": resolved_date,
        "date_source": "filename_or_document_header" if resolved_date else None,
        "source": source,
        "agenda_row_count_extracted": len(item_records),
        "items": item_records,
        "status": "SOURCE LEAD" if item_records else "EVIDENCE INCOMPLETE",
        "limitations": [
            "Extraction is a local-document text pass; verify all item numbers and wording against the final official agenda.",
            "Supporting packets, linked documents, amendments, withdrawn items, and late revisions are not fetched or authenticated.",
            "PDF extraction is text-only; no OCR is performed, so image-only scans may yield no rows.",
            "No speaker, rule-application, comparator, timing, injury, intent, protected-status, or liability finding is made.",
        ],
    }


def collect_inputs(paths: Iterable[str], input_dirs: Iterable[str]) -> list[Path]:
    found: list[Path] = []
    for value in paths:
        path = Path(value)
        if not path.is_file():
            raise FileNotFoundError(f"Input file not found: {path}")
        if path.suffix.lower() not in SUPPORTED_SUFFIXES:
            raise ValueError(f"Unsupported input file type: {path}")
        found.append(path)
    for value in input_dirs:
        root = Path(value)
        if not root.is_dir():
            raise NotADirectoryError(f"Input directory not found: {root}")
        # A directory mode accepts agenda-named files only to avoid treating
        # minutes and unrelated packet attachments as agenda sources by default.
        for path in sorted(root.rglob("*")):
            if (
                path.is_file()
                and path.suffix.lower() in SUPPORTED_SUFFIXES
                and "agenda" in path.name.casefold()
            ):
                found.append(path)
    unique: dict[Path, None] = {}
    for path in found:
        unique[path.resolve()] = None
    return sorted(unique, key=lambda item: str(item).casefold())


def build_report(
    input_paths: Sequence[Path],
    source_url: str | None = None,
    meeting_body: str | None = None,
) -> dict[str, object]:
    documents = [analyze_file(path, source_url, meeting_body) for path in input_paths]
    total_rows = sum(int(document["agenda_row_count_extracted"]) for document in documents)
    return {
        "schema_version": SCHEMA_VERSION,
        "generated_at_utc": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "overall_status": "SOURCE LEAD" if total_rows else "EVIDENCE INCOMPLETE",
        "method": "Deterministic local-document extraction and evidence checklist; no remote fetch, LLM, probability score, or legal conclusion.",
        "scope_note": (
            "Pre-meeting agenda screen only. Agenda text is a source lead, not proof of how a meeting was conducted or how an item was decided. Counts are input documents and extracted numbered rows (including section headings); duplicates and agenda revisions are not deduplicated and must not be read as unique meetings or unique matters."
        ),
        "framework_lanes": [lane for lane, _note in PATHWAY_NOTES],
        "input_document_count": len(documents),
        "agenda_row_count_extracted": total_rows,
        "documents": documents,
        "reviewer_cautions": [
            "Separate direct source observations, participant assertions, analyst inferences, unresolved matters, and contradictions.",
        "An allegation establishes only that it was made; a microphone mute requires context and is not automatically censorship; an adverse vote is not automatically retaliation or a taking; unanswered questions are not admissions.",
        "A fixed three-minute limit is not inherently unconstitutional; assess rule design separately from its application. Public warnings do not remove immunity or create clearly established law.",
        "Do not infer disability, diagnosis, protected status, identity, intent, or comparator status from names, tone, appearance, remote participation, or caption errors.",
            "Do not infer charged seconds from words or timestamps; distinguish elapsed time, pauses, technical delay, and actual charged speaking time.",
            "Keep federal constitutional, federal statutory, Wyoming constitutional/statutory, local procedural, and non-legal policy lanes separate.",
        ],
    }


def make_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Create a conservative IVIC pre-meeting screen from local agenda files. No remote scraping is performed."
    )
    parser.add_argument("--input", action="append", default=[], help="Local agenda file; may be repeated")
    parser.add_argument("--input-dir", action="append", default=[], help="Recursively read files whose names contain 'agenda'; may be repeated")
    parser.add_argument("--source-url", help="Optional source URL recorded as metadata only; never fetched")
    parser.add_argument("--meeting-body", help="Optional meeting-body label override")
    parser.add_argument("--out", default="output/municipal_analysis_report.json", help="JSON report path (default: output/municipal_analysis_report.json)")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = make_parser()
    args = parser.parse_args(argv)
    try:
        source_url = validate_source_url(args.source_url)
        input_paths = collect_inputs(args.input, args.input_dir)
        if not input_paths:
            parser.error("provide at least one --input or --input-dir containing a local agenda file")
        report = build_report(input_paths, source_url, args.meeting_body)
        output_path = Path(args.out)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    except (OSError, ValueError, RuntimeError, NotADirectoryError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    print(
        f"Wrote {output_path}: {report['input_document_count']} document(s), "
        f"{report['agenda_row_count_extracted']} extracted agenda row(s), status={report['overall_status']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
