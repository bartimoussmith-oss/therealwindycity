# Updating `therealwindycity.streamlit.app` — v5 (everything, all at once)

Same overlay-only flow as v4 (see cells below). This bundle ADDS on top of the
v4 reconciliation — your `pipeline/`, `uploads/`, scripts and corpus stay
untouched. Main file stays either twin; Cloud reboot refreshes deps.

## What's new on the site (v4 → v5)

**Live-data plumbing**
- civic-cycle now also runs: `verify_vault.py` (see below), `entity_index.py`
  (commits `Entity_Database/*.json`), `gen_feed.py` (commits `public/feed.xml`
  — an RSS feed of every watchlist hit + silent edit; feed URL once pushed:
  `https://raw.githubusercontent.com/bartimoussmith-oss/therealwindycity/main/public/feed.xml`)
- NEW workflow `meeting-watch.yml`: hourly sweep Mon/Tue evenings (the actual
  meeting windows) — 6-hour cadence is too slow for packet-night reposts.
- Masthead now prints the **true last-crawl timestamp** and a 🚨 **BREAKING
  banner** when any watchlist hit is <48 h old.
- Optional phone push: add repo secret `NTFY_TOPIC` (any random word) and the
  cycle posts commit notices to `ntfy.sh/<topic>` — subscribe in the ntfy app.
  Step auto-skips when the secret is unset. No other credentials anywhere.

**Auto-verification bridge (kills the asterisk, row by row)**
- Every vault claim is greped against the transcript corpus each cycle
  (full-string probe → 8-word-shingle fallback, deterministic, no LLM).
- Battles/Veracity/Vouchers/Environment gain a `record_evidence` column /
  badge: **✅ found in record** with file + meeting date + matched context —
  or it stays a labeled lead. Verdicts land in `data/vault_verification.json`
  (committed); if the file is absent the app re-verifies live at boot.

**New tabs (Ledger face)**
- **📰 Digest** — 7-day movement (new alerts/docs/edits), latest documents
  table, published cycle digest when present.
- **📜 Minutes Archive** — full-text search across the whole transcript corpus
  (2008→present) with verbatim, hand-checkable context snippets.
- **💡 Tips** — public intake via the new GitHub issue template
  (`.github/ISSUE_TEMPLATE/tip.md`). Tips come in; letters still only go out
  with your signature.
- Vault charts return (outcomes; spend by department) — no plotly dependency.

**Transparency Index face**
- Reads committed `Entity_Database/*.json`; if absent, **auto-indexes live**
  from the dossier corpus (gazetteer + vault names + ordinance/place regexes —
  deterministic greps). Document Viewer falls back to reading the root `.md`
  source, so dossiers render instead of "archived or unavailable".

## Colab cells (identical to v4 — overlay only, no `git rm`)

```python
# CELL 1 — upload the fresh bundle
from google.colab import files
uploaded = files.upload()   # pick realwindycity-update.tar.gz
```

```python
# CELL 2 — overlay onto the CURRENT repo and push
%cd /content
import os, subprocess
if not os.path.exists('therealwindycity'):
    !git clone https://github.com/bartimoussmith-oss/therealwindycity.git
%cd /content/therealwindycity
!git pull
!tar xzf /content/realwindycity-update.tar.gz -C /content
!cp -rf /content/deploy/. /content/therealwindycity/
!git config user.email "you@yourmail.com"
!git config user.name "bartimoussmith-oss"
!git add -A
!git commit -m "feat: mega console v5 — verification bridge, live cadence, feed + tips"
from google.colab import userdata
tok = userdata.get('GH_PAT')   # fine-grained PAT in Colab Secrets
subprocess.run(['git','push',
  f'https://{tok}@github.com/bartimoussmith-oss/therealwindycity.git'], check=True)
```

**Then:** Cloud → Manage app → ⋯ → **Reboot**. Repo **Settings → Actions →
General → Workflow permissions → Read and write** (covers both workflows).
Pass test: "Oh no." gone, sidebar face-switcher present, masthead shows a
last-crawl time, vault columns include `record_evidence`, vault metric
"verified vs corpus" starts counting up after the first cycle.

## Deliberately deferred (need you / outside pieces)

- **Live meeting captions:** Granicus serves no VTT so far (verified in
  pipeline README) — the path is stream-capture, not fetch. Doable later.
- **Check-register verification of voucher rows:** needs the city's current
  disbursement endpoint located (or a records request — human sends it).
- **Turnstile on the tip form:** GitHub issues already carry spam controls;
  add a webform only if volume demands it.
- **uploads/ (~70 MB):** intentionally outside the in-app readers; moving it
  to a Release asset keeps clones lean whenever Colab pulls feel slow.
