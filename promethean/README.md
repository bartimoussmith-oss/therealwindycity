# Promethean safe federation

This additive implementation adapts the two owner-supplied payloads without replacing existing applications or agent safeguards. Automatic accusations, fabricated fallback conflicts, blanket pushes and first-available-rclone copying are not implemented. Repository discovery does not grant access or make web routes live.

Install dependencies explicitly: `python -m pip install -r promethean/requirements.txt`.

- Inspect: `python omnibus_agent_sdk.py status`
- Initialize local storage: `python omnibus_agent_sdk.py init-db`
- Search: `python omnibus_agent_sdk.py query --match 'annexation'`
- Harvest: `python omnibus_agent_sdk.py harvest-granicus --url 'SPECIFIC_MEETING_HTTPS_URL' --committee 'VERIFIED_BODY' --date YYYY-MM-DD`
- Review claim: `python omnibus_agent_sdk.py audit-claim --official 'NAME' --date YYYY-MM-DD --claim 'EXACT_QUOTE'`
- Optional local model: append `--llm-endpoint http://127.0.0.1:8080/v1/chat/completions`. Evidence stays local; model output remains unreviewed.
- Graph: `python omnibus_agent_sdk.py build-graph --export-json /path/outside/repo/graph.json`
- Dashboard: `streamlit run promethean/dashboard.py`

The default database and downloaded evidence live outside git. Existing databases are not migrated automatically; explicitly select and back up a compatible SQLite file before using `--db`. The shared core is not an adapter for every existing database schema. Graphs currently link documents to textual ordinance/resolution mentions only, not contractors or inferred personal relationships. PDF extraction flags blank text as requiring OCR; it does not perform OCR. Caller-supplied meeting metadata needs source verification. Bounded traversal can miss JavaScript-only attachments and intentionally refuses publisher-wide meeting/date attribution.

Manual workflow outputs are seven-day review artifacts. It has read-only repository permissions, no schedule, no auto-commit and no publishing. No live harvest, model server, browser deployment, Streamlit route, Google Drive bridge, Cloud Run service or SpiderFoot integration is verified by installing these files. Package versions are bounded but not hash-locked; review dependencies before operational use.
