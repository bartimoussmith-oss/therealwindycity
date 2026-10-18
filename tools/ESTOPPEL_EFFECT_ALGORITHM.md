# Estoppel-Effect Candidate Algorithm

**Status:** additive research tooling and analyst runbook<br>
**Version:** `1.0.0`<br>
**Last validated:** 2026-10-18

## Purpose and boundary

`estoppel_effect.py` is a reproducible, source-aware research aid for finding phrase-pattern candidates relevant to the estoppel-effect framework in the white paper. It extracts local excerpts from the available caption-aligned intervention index and, optionally, the normalized meeting-transcript corpus; preserves source links, dates, offsets, alignment and duplicate metadata, and text hashes; and ranks possible same-meeting and cross-meeting comparisons for human review.

It is not a legal decision system. It does **not** decide that a statement is true, attributable, an assurance, notice, a contradiction, a violation, reliance, prejudice, causation, or estoppel. It does not infer a speaker from the meeting-level corpus. A recorded objection, phrase match, time sequence, or silence is not automatically actual notice or a legal consequence.

The algorithm does not edit inputs or existing normalization/indexing tools. It writes only the requested derived JSON and optional CSV output. Use `/tmp` or another ignored location for generated reports.

## Inputs

Defaults are repository-relative:

- `pipeline/miller_interventions.json` — caption-aligned `turn` and `context` cue blocks, with video IDs, timestamps, dates, alignment scores, and overlap groups.
- `drive-import/master_meetings_database.json.gz` — optional meeting-level transcript context, loaded through the existing `tools/ai_record_drive.py` normalization route.

Use `--no-meetings-db` to run only against the intervention index. The linked master and other recovery artifacts are not implied inputs; the algorithm does not process the separately described recovery bundles that are absent from this checkout.

### Provenance and deduplication

Intervention rows are grouped by `(video, block, dup_group)`. For each group, the selected alternative is the highest-quality non-truncated row, ordered by alignment score, duration, and then duplicate rank. Other variants are retained as metadata, not counted as independent records. The alignment score is a lexical alignment measure, **not** a probability of correct attribution or timing.

The meeting-level normalizer's exact-duplicate records (`dup_of`) are excluded from primary text processing and counted in input metadata. This does not establish that remaining transcripts are independent of the cue index: both may ultimately derive from captions for the same recording.

The JSON report records a SHA-256 for each input file. Each normalized source text also receives a SHA-256 after whitespace collapsing and case-folding. Event records retain source IDs and source metadata; character offsets refer to the loaded source text, not an external original file's byte offsets. The intervention cue URL includes the selected video timestamp.

## Phrase-signal catalogue

The eight tactic-oriented tags are deliberately phrase-based:

1. `assurance_to_instrument` — assurance/permanence language and requests to identify written, adopted, or binding text.
2. `predecision_evidence_gap` — language that a report, study, data, or analysis was missing or unavailable before a decision.
3. `analytical_bridge` — questions or statements connecting evidence/reasoning to a criterion, finding, or decision.
4. `cross_speaker_comparison` — comparison of standards, treatment, rules, or opportunities for different speakers.
5. `operative_text_narrowing` — proposed amendment, deletion, replacement, or addition of operative language.
6. `cross_meeting_chronology` — references to prior meetings/statements or an asserted change in position or explanation.
7. `notice_opportunity_to_cure` — record-building, correction, clarification, preservation, or cure requests.
8. `fiscal_explanation_testing` — funding, budget, allocation, or competing-priority language.

Three additional diagnostic groups are reported separately from those eight tactics: `legal_claim_marker`, `decision_action_marker`, and `reliance_prejudice_cue`. They flag terms for review; they do not decide a legal element or outcome. Patterns can miss paraphrases or match quotation, hypothetical, negated, or irrelevant language. A local negation flag is saved for review, but stance is not inferred.

## Processing steps

1. **Load and normalize.** Validate dates where available, normalize meeting-body labels, preserve input metadata, and omit exact duplicates according to the existing meeting normalizer.
2. **Find phrase matches.** Apply the compiled, case-insensitive patterns. Each match retains its tag, matched text, and character/word offsets. Exact duplicate hits with the same tag and offsets are collapsed.
3. **Group nearby hits.** Hits in a record are clustered when they are no more than 70 whitespace-delimited words apart and the cluster spans no more than 130 words from its first hit. Each event excerpt includes up to 45 words before the first hit and 65 words after the last hit. Multiple tags inside one cluster produce one event, not multiple independent observations.
4. **Preserve evidence.** Each event includes the source-linked excerpt, source-text hash, offsets, signal tags, date/body/title metadata, attribution caveat, and a review-only status. A `turn` cue receives the index's “Miller” label but is explicitly marked as not independently audio-verified. `context` and meeting-level records are not assigned to a speaker by this algorithm.
5. **Rank possible comparisons.** Normalize issue tokens; remove common language, recurrent local names, and parliamentary/roll-call boilerplate; downweight terms appearing in more than 20% of event excerpts; retain up to 10 high-IDF terms per event for pair generation and cosine scoring. The minimum similarity defaults to `0.08`. The score is lexical, corpus-dependent, and not calibrated as confidence or probability.

### Comparison types and default safeguards

- **`same_meeting_source_crosscheck`** — same-date, same-body cue and meeting-level text. The Miller cue must contain a tactic-pattern candidate; the meeting-level excerpt can be context only. The record A/B ordering is for display and does not imply chronology. The pair is not independent corroboration unless source independence is separately established.
- **`same_meeting_sequence_candidate`** — a Miller cue and a context cue from the same video/date, with the context cue's start timestamp after the Miller cue's end timestamp. A tactic-pattern candidate is required in the Miller cue. This is a sequence lead, not proof that a later statement was a response or cure.
- **`cross_meeting_chronology_candidate`** — valid, date-ordered records from the same normalized body by default, within 3,650 days. Both records must have at least one tactic-pattern candidate. They must share at least three issue tokens, have at least one shared term retained in the high-IDF vectors, and meet the cosine threshold. If the later record has a `cross_meeting_chronology` phrase match, the shared-token floor is reduced to one; the similarity threshold and at-least-one shared high-IDF term requirement still apply. The default output keeps up to three high-ranked comparison leads per Miller cue anchor.

The CLI's `--min-shared-terms` sets the general floor, but cross-meeting candidates without a later chronology phrase always require at least three shared tokens. Enabling `--allow-cross-body` relaxes the body restriction and should be used only for an intentional cross-body search. No relation type is a finding that the excerpts concern the same proposition.

The reported `candidate_rank_score` is cosine similarity plus small ranking boosts for a later chronology phrase and overlapping tactic tags. It may exceed 1.0, has no calibrated interpretation, and must not be represented as probability, confidence, severity, or legal strength. Candidate selection is a bounded review queue, not a claim that the highest-ranked pair is the “best contradiction.”

## Runbook

From the repository root:

```bash
python -m py_compile tools/estoppel_effect.py tools/test_estoppel_effect.py
python -m unittest discover -s tools -p 'test_estoppel_effect.py' -v
python tools/estoppel_effect.py \
  --out /tmp/estoppel-effect-audit.json \
  --review-csv /tmp/estoppel-effect-review.csv
```

For a cue-index-only run:

```bash
python tools/estoppel_effect.py --no-meetings-db \
  --out /tmp/estoppel-effect-cues-only.json
```

Useful options include `--interventions`, `--meetings-db`, `--min-alignment-score`, `--no-context`, `--min-shared-terms`, `--min-similarity`, `--top-per-miller-event`, `--max-date-gap-days`, and `--allow-cross-body`. Run `python tools/estoppel_effect.py --help` for the current CLI. The report embeds the input-file hashes and processing thresholds so runs can be compared.

### Outputs

- **JSON audit report** — run metadata and hashes, input/deduplication counts, event counts by source role and signal, the complete event list, ranked comparison candidates, and unfilled analyst-review fields.
- **Optional CSV queue** — compact excerpts, source links, tags, shared terms, scores, and blank/unassessed human-review status fields. The JSON remains the provenance-rich source of truth.

The review fields intentionally remain unassessed (`same_issue`, `same_proposition`, `same_scope_and_stage`, `same_authority_or_speaker`, intervening facts, response/cure, contradiction, causal link, and legal effect).

## Live Streamlit integration

`pages/23_Estoppel_Effect.py` exposes the review queue in the Streamlit multipage app. The feature is linked from the home page in both identical app entrypoints. The analysis runs automatically when a visitor opens the page; the home-page preview stays fast and does not compute it. The read-only report is cached using the SHA-256 hashes of the intervention index and, when included, the meeting transcript database. A changed input hash invalidates that cache. A **Rebuild analysis now** button clears the cached report; after deployment, the first page visit takes about 40 seconds on the validation corpus, while later visits reuse the cached report.

The website only receives this code after the change is merged into the app's deployed `main` branch. Per the repository quickstart, Streamlit Community Cloud runs from this repository; allow its normal redeploy after merge. The page does not modify the source files or auto-post its output elsewhere.

## Human review protocol

For every retained candidate:

1. Open the source video or official record at the stored date/time; confirm wording, context, speaker, transcription accuracy, and whether the cue excerpt crosses speaker boundaries.
2. Check whether the records concern the same issue **and** same proposition, scope, procedural stage, and decision-maker/authority.
3. Establish chronology from the original source. Separate a same-meeting transcript cross-check from an independent source; do not infer sequence where timestamps are unavailable.
4. Search for intervening facts, revised documents, correction, response, cure, official action, or an explanation. Record each with its own source.
5. Assess actual notice, reliance, detriment/prejudice, causation, authority, and legal effect only through human review of the full evidence and governing law. Do not treat a recorded objection as automatic notice, violation, or estoppel.

## Validation snapshot (2026-10-18)

The final smoke run compiled the algorithm and processed the available local inputs without modifying them:

- 616 intervention-index rows grouped into 291 selected cue records: 228 `turn` labels and 63 context cues; 325 alignment alternatives retained as non-independent metadata.
- 720 meeting-database records read; 635 primary text records processed and 85 exact-duplicate records omitted. The normalizer reported 35 dates inferred from titles and 180 records with an unknown/invalid date.
- 926 combined source records yielded 7,678 phrase-event clusters: 222 Miller-labelled, 50 context-cue, and 7,406 unattributed meeting-context events.
- 479 ranked comparison leads: 200 cross-meeting chronology candidates, 8 timestamp-sequence candidates, and 271 same-meeting source cross-checks.
- Signal counts were: 1,912 assurance-to-instrument; 25 predecision-evidence-gap; 74 analytical-bridge; 338 cross-speaker-comparison; 504 operative-text-narrowing; 729 cross-meeting-chronology; 902 notice/opportunity-to-cure; and 424 fiscal-explanation-testing matches.
- Seven standard-library tests passed, covering offsets/hashes, duplicate alignment handling, boilerplate filtering, cross-meeting safeguards, same-meeting chronology behavior, and CSV output.

All counts are pattern/event candidates, not distinct verified statements or meetings. Spot inspection showed a mix of useful issue-specific leads and noisy lexical overlaps; even candidates with several shared terms require source and proposition review. This run did not independently review all City of Cheyenne 2026 YouTube videos, process the absent recovery bundles, verify the pasted inventory counts, or decide any legal question.
