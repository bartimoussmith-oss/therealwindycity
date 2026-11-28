#!/usr/bin/env python3
"""R2PO-Enforced Read-Only Export: Promethean Vault -> The Real Windy City Public Snapshot."""
import argparse, hashlib, json, os, re, sqlite3
from datetime import datetime, timezone
from pathlib import Path

SECRET_RE = re.compile(r"(ghp_|github_pat_|sk-[A-Za-z0-9]{20,}|AKIA[0-9A-Z]{16}|BEGIN PRIVATE KEY)", re.I)

def open_ro(path: Path):
    if not path or not path.exists():
        return None
    conn = sqlite3.connect(f"file:{path.resolve()}?mode=ro", uri=True, timeout=5.0)
    conn.row_factory = sqlite3.Row
    return conn

def q_rows(conn, sql, params=()):
    if conn is None:
        return []
    try:
        return [dict(r) for r in conn.execute(sql, params).fetchall()]
    except Exception:
        return []

def clean(rec: dict) -> dict:
    out = {}
    for k, v in rec.items():
        if k in ("full_text", "raw_credentials"):
            continue
        out[k] = "[REDACTED]" if (isinstance(v, str) and SECRET_RE.search(v)) else v
    return out

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--vault", default="/home/ubuntu/promethean_fortress/vault/promethean_omni_vault.db")
    ap.add_argument("--rwc-repo", default="/home/ubuntu/repos/therealwindycity")
    ap.add_argument("--private-out", default="/home/ubuntu/promethean-national-core/private_review")
    args = ap.parse_args()

    rwc = Path(args.rwc_repo).resolve()
    vault = open_ro(Path(args.vault))
    wd = open_ro(rwc / "cheyenne_watchdog.db")

    wy_towns = [clean(r) for r in q_rows(vault, """
        SELECT municipality, county, tier AS access_tier, domain, remote_comment, email,
               wayback_pdfs_found, wayback_tamper_alerts, tier_a_defects,
               nullification_status, last_audited_utc
        FROM wy_99_municipalities
        ORDER BY tier_a_defects DESC, wayback_tamper_alerts DESC, municipality ASC
    """)]
    wy_verified = [clean(r) for r in q_rows(vault, """
        SELECT municipality, county, meeting_date, doc_type, url, wayback_ts,
               captured_utc, sha256, evidence_tier, flags_json
        FROM wy_wpma_documents
        WHERE evidence_tier IN ('TIER_A','TIER_B','EVID_TIER_A_FACIAL','EVID_TIER_B_TRANSCRIPT')
        ORDER BY meeting_date DESC, municipality ASC LIMIT 500
    """)]
    wy_tier_c = [clean(r) for r in q_rows(vault, """
        SELECT municipality, county, meeting_date, doc_type, url, sha256, evidence_tier, flags_json
        FROM wy_wpma_documents
        WHERE evidence_tier IN ('TIER_C','EVID_TIER_C_WPRA_PENDING')
        ORDER BY meeting_date DESC LIMIT 500
    """)]
    tamper = [clean(r) for r in q_rows(vault, """
        SELECT municipality, original_url, earliest_ts, latest_ts,
               earliest_digest, latest_digest, unique_versions, detected_utc
        FROM wy_wayback_tamper_alerts ORDER BY detected_utc DESC LIMIT 250
    """)]
    nationwide = []
    for r in q_rows(vault, """
        SELECT domain, org_name, domain_type, city, state, platform, agenda_url,
               legistar_client, has_zoom_comment, wayback_pdf_count, tamper_count,
               illegality_score, composite_score, flags_json, last_scanned_utc
        FROM panopticon_municipalities
        ORDER BY illegality_score DESC, tamper_count DESC, composite_score DESC LIMIT 200
    """):
        cr = clean(r)
        try:
            cr["flags"] = [f for f in json.loads(cr.pop("flags_json", "[]") or "[]") if not f.startswith("PRIVATE_")]
        except Exception:
            cr["flags"] = []
        nationwide.append(cr)

    contradictions = [clean(r) for r in q_rows(wd, "SELECT * FROM veracity_contradictions LIMIT 100")]
    battles = [clean(r) for r in q_rows(wd, "SELECT * FROM public_comment_battles LIMIT 100")]
    if vault: vault.close()
    if wd: wd.close()

    now = datetime.now(timezone.utc).isoformat()
    pub = {
        "schema_version": "4.0.0-rwc-sunshine",
        "publication_tier": "PUB_TIER_1_PUBLIC",
        "evidence_gate": "EVID_TIER_A_FACIAL + EVID_TIER_B_TRANSCRIPT ONLY",
        "generated_utc": now,
        "summary_metrics": {
            "wyoming_municipalities_tracked": len(wy_towns),
            "wyoming_verified_defects": len(wy_verified),
            "wayback_tamper_alerts": len(tamper),
            "nationwide_municipalities_indexed": len(nationwide),
            "cheyenne_contradictions_linked": len(contradictions),
            "cheyenne_battles_linked": len(battles),
        },
        "wyoming_99_scorecard": wy_towns,
        "wyoming_verified_wpma_ledger": wy_verified,
        "wayback_tampering_alerts": tamper,
        "nationwide_sunshine_index": nationwide,
        "cheyenne_watchdog_bridge": {
            "veracity_contradictions": contradictions,
            "public_comment_battles": battles,
        },
    }
    raw = json.dumps(pub, indent=2)
    if SECRET_RE.search(raw):
        raise SystemExit("[ABORT] Secret pattern detected in public export.")

    for out_path in (rwc / "data" / "sunshine_public_export.json", rwc / "public" / "sunshine_scorecard.json"):
        out_path.write_text(raw, encoding="utf-8")
    print(f"[R2PO-OK] Exported PUB_TIER_1_PUBLIC snapshot sha256={hashlib.sha256(raw.encode()).hexdigest()[:12]}")
    print("          Metrics:", json.dumps(pub["summary_metrics"]))

    pdir = Path(args.private_out)
    pdir.mkdir(parents=True, exist_ok=True)
    pfile = pdir / "tier_c_review_queue.json"
    pfile.write_text(json.dumps({"publication_tier": "PUB_TIER_3_PRIVATE_REVIEW", "generated_utc": now, "wyoming_tier_c_queue": wy_tier_c}, indent=2), encoding="utf-8")
    os.chmod(pfile, 0o600)

if __name__ == "__main__":
    main()
