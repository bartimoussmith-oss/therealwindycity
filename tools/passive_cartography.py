#!/usr/bin/env python3
"""Passive OSINT Statewide Infrastructure Cartographer & Vendor PRA Matrix Builder.

Implements the hybrid "GitHub Actions Matrix -> Colab / Streamlit" pipeline:
  1. Target Matrix Manifest (`wyoming/targets.json` reconciled with `wyoming/registry.json`).
  2. Strict Passive-Only Policy Gate (`validate_spiderfoot_modules` — refuses active port
     scans `sfp_portscan_tcp`, vulnerability scanners, and brute-force modules).
  3. Personal-PII Guard (`filter_institutional_contacts` — strips personal individual
     emails per LEGAL.md §5, keeping only generic institutional role addresses).
  4. Passive DNS + Certificate Transparency (`crt.sh`) + polite robots-aware HTTPS header/HTML
     SaaS vendor fingerprinting across 15 civic software stacks, with optional SpiderFoot
     passive CLI integration (`--use-spiderfoot`).
  5. Automatic SHA-256 + CASE/UCO provenance sidecars via `promethean.forensic_audit`.
  6. SQLite + JSON + Markdown Consolidator (`consolidate`) that merges per-county matrix
     artifacts into `wyoming_statewide_records_infrastructure.db` and generates human-reviewed
     W.S. 16-4-202 DRAFT templates tailored to each jurisdiction's detected vendor stack.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import ipaddress
import json
from pathlib import Path
import re
import shutil
import socket
import sqlite3
import subprocess
import sys
import time
from typing import Any, Iterable, Mapping
import urllib.error
import urllib.parse
import urllib.request
import urllib.robotparser

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from promethean.forensic_audit import (  # noqa: E402
    MIRROR_LEDGERS,
    build_arcgis_geojson_query_url,
    package_osint_artifact,
    verify_osint_provenance,
)

TARGETS_PATH = ROOT / "wyoming" / "targets.json"
REGISTRY_PATH = ROOT / "wyoming" / "registry.json"
UA = "WyomingCivicCartography/1.0 (+https://github.com/bartimoussmith-oss/therealwindycity; passive public-records infrastructure inventory)"

ALLOWED_PASSIVE_SPIDERFOOT_MODULES = frozenset({
    "sfp_crt",
    "sfp_dnsresolve",
    "sfp_whois",
    "sfp_webframework",
    "sfp_wappalyzer",
    "sfp_email",
    "sfp_accounts",
})

BLOCKED_ACTIVE_MODULE_TOKENS = (
    "portscan",
    "nmap",
    "nuclei",
    "vuln",
    "sql",
    "xss",
    "brute",
    "dirbrute",
    "nikto",
    "masscan",
    "shodan",
    "zmap",
    "exploit",
)

INSTITUTIONAL_ROLE_PREFIXES = frozenset({
    "clerk", "cityclerk", "countyclerk", "townclerk",
    "records", "publicrecords", "openrecords", "foia", "pra",
    "assessor", "treasurer", "finance", "purchasing", "ap",
    "gis", "mapping", "planning", "permits", "building", "codeenforcement",
    "utilities", "bopu", "publicworks", "water", "engineering",
    "council", "commissioners", "bocc", "administration", "admin",
    "info", "contact", "general", "webmaster", "it", "support",
})

EMAIL_RE = re.compile(r"\b([a-zA-Z0-9._%+-]{1,64})@([a-zA-Z0-9.-]+\.[a-zA-Z]{2,24})\b")
ARCGIS_URL_RE = re.compile(
    r"https://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._~:/?#\[\]@!$&'()*+,;=%-]*)?/(?:MapServer|FeatureServer)(?:/\d+)?",
    re.IGNORECASE,
)
REST_SERVICES_URL_RE = re.compile(
    r"https://[a-zA-Z0-9.-]+(?:/[a-zA-Z0-9._~-]*)*/rest/services\b",
    re.IGNORECASE,
)

VENDOR_SIGNATURES: tuple[dict[str, Any], ...] = (
    {
        "vendor_id": "govqa",
        "label": "Granicus GovQA Public Records Portal",
        "category": "public_records_portal",
        "section_id": 7,
        "patterns": (r"\bgovqa\.us\b", r"\bmycusthelp\.com\b", r"\bwebqa\b"),
    },
    {
        "vendor_id": "nextrequest",
        "label": "CivicPlus NextRequest Public Records Portal",
        "category": "public_records_portal",
        "section_id": 7,
        "patterns": (r"\bnextrequest\.com\b",),
    },
    {
        "vendor_id": "granicus",
        "label": "Granicus Legislative / Agenda Platform",
        "category": "legislative_agendas",
        "section_id": 1,
        "patterns": (r"\bgranicus\.com\b", r"generatedagendaviewer", r"viewpublisher\.php"),
    },
    {
        "vendor_id": "civicplus",
        "label": "CivicPlus / AgendaCenter / CivicClerk",
        "category": "legislative_agendas",
        "section_id": 1,
        "patterns": (r"/agendacenter\b", r"\bcivicplus\b", r"\bcivicengage\b", r"\bcivicclerk\b"),
    },
    {
        "vendor_id": "boarddocs",
        "label": "BoardDocs Agenda Governance",
        "category": "legislative_agendas",
        "section_id": 1,
        "patterns": (r"\bboarddocs\.com\b",),
    },
    {
        "vendor_id": "municode",
        "label": "Municode / CivicPlus Ordinance & Meeting Library",
        "category": "legislative_agendas",
        "section_id": 1,
        "patterns": (r"\bmunicode\.com\b",),
    },
    {
        "vendor_id": "tyler_itax_eagle",
        "label": "Tyler Technologies (ERP / iTax / Eagle Recorder)",
        "category": "tax_cama_erp",
        "section_id": 2,
        "patterns": (r"\btylertech\.com\b", r"\btylerhost\.net\b", r"\bitax\b", r"\beagleweb\b"),
    },
    {
        "vendor_id": "greenwood_gis",
        "label": "Greenwood Mapping County Assessor/GIS Portal",
        "category": "gis_parcel_portal",
        "section_id": 4,
        "patterns": (r"\bgreenwoodmap\.com\b", r"greenwood\s+mapping"),
    },
    {
        "vendor_id": "esri_arcgis",
        "label": "Esri ArcGIS Server / ArcGIS Hub",
        "category": "gis_arcgis_rest",
        "section_id": 4,
        "patterns": (r"\barcgis\.com\b", r"/rest/services\b", r"/mapserver\b", r"/featureserver\b"),
    },
    {
        "vendor_id": "opengov_viewpoint",
        "label": "OpenGov / ViewPoint Cloud Permitting & Transparency",
        "category": "permitting_transparency",
        "section_id": 3,
        "patterns": (r"\bviewpointcloud\.com\b", r"\bopengov\.com\b"),
    },
    {
        "vendor_id": "smartgov",
        "label": "Brightly SmartGov Permitting Portal",
        "category": "permitting_transparency",
        "section_id": 3,
        "patterns": (r"\bsmartgovcommunity\.com\b", r"\bsmartgov\b"),
    },
    {
        "vendor_id": "socrata",
        "label": "Tyler Socrata Open Finance / Data Portal",
        "category": "open_data_ledger",
        "section_id": 2,
        "patterns": (r"\bsocrata\.com\b", r"\bwyopen\.gov\b"),
    },
    {
        "vendor_id": "hsgovtech",
        "label": "HSGovTech / HealthSpace Environmental Health",
        "category": "environmental_health",
        "section_id": 5,
        "patterns": (r"\bhealthspace\.com\b", r"\bhsgovtech\b"),
    },
    {
        "vendor_id": "flock_safety",
        "label": "Flock Safety ALPR Transparency Portal",
        "category": "alpr_transparency",
        "section_id": 6,
        "patterns": (r"\bflocksafety\.com\b",),
    },
    {
        "vendor_id": "mimecast_gateway",
        "label": "Mimecast Archival / Security SMTP Gateway",
        "category": "smtp_archival_gateway",
        "section_id": 7,
        "patterns": (r"\bmimecast\.com\b",),
    },
)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_targets(path: Path = TARGETS_PATH) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    targets = data.get("targets", [])
    if not targets:
        raise ValueError("wyoming/targets.json contains zero targets")
    slugs = [t["jurisdiction"] for t in targets]
    if len(set(slugs)) != len(slugs):
        raise ValueError("Duplicate jurisdiction slug in wyoming/targets.json")
    return data


def validate_spiderfoot_modules(modules: str | Iterable[str]) -> list[str]:
    """Fail closed if any active/intrusive SpiderFoot module is requested."""
    if isinstance(modules, str):
        items = [m.strip() for m in modules.split(",") if m.strip()]
    else:
        items = [str(m).strip() for m in modules if str(m).strip()]
    if not items:
        raise ValueError("At least one passive SpiderFoot module is required")
    for mod in items:
        low = mod.lower()
        if any(tok in low for tok in BLOCKED_ACTIVE_MODULE_TOKENS):
            raise ValueError(
                f"Active/intrusive module '{mod}' is prohibited by repository and cloud AUP policy; "
                f"allowed passive modules: {sorted(ALLOWED_PASSIVE_SPIDERFOOT_MODULES)}"
            )
        if mod not in ALLOWED_PASSIVE_SPIDERFOOT_MODULES:
            raise ValueError(
                f"Unapproved SpiderFoot module '{mod}'; allowed passive modules: "
                f"{sorted(ALLOWED_PASSIVE_SPIDERFOOT_MODULES)}"
            )
    return items


def filter_institutional_contacts(raw_texts_or_emails: Iterable[str]) -> dict[str, Any]:
    """Extract only generic official/custodian role email addresses; redact personal individual emails."""
    retained: set[str] = set()
    redacted_count = 0
    for chunk in raw_texts_or_emails:
        for match in EMAIL_RE.finditer(chunk or ""):
            local_part = match.group(1).lower()
            domain_part = match.group(2).lower()
            normalized_prefix = re.sub(r"[^a-z0-9]", "", local_part)
            if local_part in INSTITUTIONAL_ROLE_PREFIXES or normalized_prefix in INSTITUTIONAL_ROLE_PREFIXES:
                retained.add(f"{local_part}@{domain_part}")
            else:
                redacted_count += 1
    return {
        "institutional_role_contacts": sorted(retained),
        "redacted_personal_or_nonrole_email_count": redacted_count,
    }


def fingerprint_saas_vendors(
    subdomains: Iterable[str] = (),
    mx_records: Iterable[str] = (),
    headers: Mapping[str, Any] | None = None,
    html_samples: Iterable[str] = (),
) -> dict[str, Any]:
    """Identify civic SaaS and public-records portals from passive DNS/CT/header/HTML signals."""
    corpus_parts: list[str] = []
    corpus_parts.extend(str(s) for s in subdomains)
    corpus_parts.extend(str(m) for m in mx_records)
    if headers:
        for k, v in headers.items():
            corpus_parts.append(f"{k}: {v}")
    corpus_parts.extend(str(h) for h in html_samples)
    combined = "\n".join(corpus_parts)

    detected: list[dict[str, Any]] = []
    for sig in VENDOR_SIGNATURES:
        matched_patterns: list[str] = []
        for pat in sig["patterns"]:
            m = re.search(pat, combined, re.IGNORECASE)
            if m:
                matched_patterns.append(m.group(0)[:120])
        if matched_patterns:
            detected.append({
                "vendor_id": sig["vendor_id"],
                "label": sig["label"],
                "category": sig["category"],
                "section_id": sig["section_id"],
                "evidence_tokens": sorted(set(matched_patterns)),
                "status": "candidate_unreviewed",
            })

    arcgis_layers: set[str] = set()
    arcgis_roots: set[str] = set()
    for m in ARCGIS_URL_RE.finditer(combined):
        arcgis_layers.add(m.group(0).rstrip("/"))
    for m in REST_SERVICES_URL_RE.finditer(combined):
        arcgis_roots.add(m.group(0).rstrip("/"))

    geojson_queries: list[dict[str, str]] = []
    for layer_url in sorted(arcgis_layers)[:25]:
        try:
            qurl = build_arcgis_geojson_query_url(layer_url)
            geojson_queries.append({"service_url": layer_url, "geojson_query_url": qurl})
        except ValueError:
            continue

    return {
        "detected_vendors": detected,
        "arcgis_rest_roots": sorted(arcgis_roots),
        "arcgis_geojson_queries": geojson_queries,
    }


def _resolve_passive_dns(domain: str) -> dict[str, Any]:
    ips: set[str] = set()
    errors: list[str] = []
    try:
        for res in socket.getaddrinfo(domain, 443, type=socket.SOCK_STREAM):
            addr = res[4][0]
            if ipaddress.ip_address(addr).is_global:
                ips.add(addr)
    except OSError as exc:
        errors.append(f"A/AAAA lookup: {exc}")

    mx_hosts: set[str] = set()
    ns_hosts: set[str] = set()
    # Best-effort passive MX/NS via dig or nslookup if present on runner
    dig_bin = shutil.which("dig")
    if dig_bin:
        for rtype, sink in (("MX", mx_hosts), ("NS", ns_hosts)):
            try:
                proc = subprocess.run(
                    [dig_bin, "+short", "+time=3", "+tries=1", domain, rtype],
                    capture_output=True, text=True, timeout=5, check=False,
                )
                for line in proc.stdout.splitlines():
                    tok = line.strip().rstrip(".").split()[-1].lower() if line.strip() else ""
                    if tok and "." in tok:
                        sink.add(tok)
            except Exception as exc:
                errors.append(f"dig {rtype}: {exc}")
    return {
        "public_ips": sorted(ips),
        "mx_records": sorted(mx_hosts),
        "ns_records": sorted(ns_hosts),
        "dns_errors": errors,
    }


def _query_crt_sh(domain: str, timeout: float = 10.0) -> tuple[list[str], str | None]:
    """Query public Certificate Transparency logs (crt.sh JSON output) passively."""
    url = f"https://crt.sh/?q=%25.{urllib.parse.quote(domain)}&output=json"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(2_000_000)
        payload = json.loads(raw.decode("utf-8", errors="replace"))
        subs: set[str] = set()
        if isinstance(payload, list):
            for entry in payload[:1500]:
                if not isinstance(entry, Mapping):
                    continue
                for line in str(entry.get("name_value", "")).splitlines():
                    host = line.strip().lower().lstrip("*.")
                    if host and (host == domain.lower() or host.endswith("." + domain.lower())):
                        subs.add(host)
        return sorted(subs)[:250], None
    except Exception as exc:
        return [], f"{type(exc).__name__}: {exc}"


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _polite_https_fingerprint(domain: str, timeout: float = 8.0) -> dict[str, Any]:
    """Perform a single polite robots.txt-respecting HTTPS check on port 443."""
    opener = urllib.request.build_opener(_NoRedirect())
    current_url = f"https://{domain}/"
    robots_url = f"https://{domain}/robots.txt"
    robots_allowed = True

    try:
        r_req = urllib.request.Request(robots_url, headers={"User-Agent": UA})
        with opener.open(r_req, timeout=timeout) as r_resp:
            if r_resp.status == 200:
                r_text = r_resp.read(200_000).decode("utf-8", errors="replace")
                if "<html" not in r_text.lower():
                    rp = urllib.robotparser.RobotFileParser()
                    rp.parse(r_text.splitlines())
                    robots_allowed = rp.can_fetch(UA, current_url)
    except urllib.error.HTTPError as exc:
        if exc.code not in (404, 301, 302, 307, 308):
            robots_allowed = False
    except Exception:
        pass

    if not robots_allowed:
        return {
            "url": current_url,
            "reachable": False,
            "robots_allowed": False,
            "status_code": None,
            "headers": {},
            "html_excerpt": "",
            "error": "Skipped HTML fetch: disallowed by robots.txt",
        }

    # Follow up to 3 HTTPS-only public redirects manually
    visited_url = current_url
    for _ in range(4):
        parsed = urllib.parse.urlsplit(visited_url)
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            return {
                "url": visited_url,
                "reachable": False,
                "robots_allowed": True,
                "status_code": None,
                "headers": {},
                "html_excerpt": "",
                "error": "Non-HTTPS redirect target not followed",
            }
        try:
            req = urllib.request.Request(visited_url, headers={"User-Agent": UA})
            with opener.open(req, timeout=timeout) as resp:
                hdrs = {k: v for k, v in resp.headers.items() if k.lower() in (
                    "server", "content-type", "x-powered-by", "cf-ray", "x-aspnet-version", "strict-transport-security",
                )}
                body = resp.read(500_000).decode("utf-8", errors="replace")
                return {
                    "url": visited_url,
                    "reachable": resp.status == 200,
                    "robots_allowed": True,
                    "status_code": resp.status,
                    "headers": hdrs,
                    "html_excerpt": body[:250_000],
                    "error": None,
                }
        except urllib.error.HTTPError as exc:
            if exc.code in (301, 302, 303, 307, 308) and exc.headers.get("Location"):
                visited_url = urllib.parse.urljoin(visited_url, exc.headers["Location"])
                continue
            return {
                "url": visited_url,
                "reachable": False,
                "robots_allowed": True,
                "status_code": exc.code,
                "headers": {},
                "html_excerpt": "",
                "error": f"HTTP {exc.code}",
            }
        except Exception as exc:
            return {
                "url": visited_url,
                "reachable": False,
                "robots_allowed": True,
                "status_code": None,
                "headers": {},
                "html_excerpt": "",
                "error": f"{type(exc).__name__}: {exc}",
            }

    return {
        "url": visited_url,
        "reachable": False,
        "robots_allowed": True,
        "status_code": None,
        "headers": {},
        "html_excerpt": "",
        "error": "Redirect limit exceeded",
    }


def _run_optional_spiderfoot_passive(
    domain: str,
    modules: list[str],
    timeout_sec: int = 360,
) -> dict[str, Any]:
    """Run SpiderFoot CLI strictly in passive mode if `sf.py` or `spiderfoot` is installed."""
    validated = validate_spiderfoot_modules(modules)
    sf_cmd = shutil.which("spiderfoot") or shutil.which("sf.py")
    if not sf_cmd:
        return {"invoked": False, "reason": "SpiderFoot CLI not installed on host; used built-in passive cartographer."}
    cmd = [sf_cmd, "-s", domain, "-m", ",".join(validated), "-o", "json", "-q"]
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_sec, check=False)
        events = json.loads(proc.stdout) if proc.stdout.strip().startswith("[") else []
        subdomains: set[str] = set()
        texts: list[str] = []
        for ev in events if isinstance(events, list) else []:
            if not isinstance(ev, Mapping):
                continue
            etype = str(ev.get("type", ""))
            edata = str(ev.get("data", ""))
            if etype in ("INTERNET_NAME", "AFFILIATE_INTERNET_NAME") and edata:
                subdomains.add(edata.strip().lower())
            elif etype in ("WEBSERVER_TECHNOLOGY", "TARGET_WEB_CONTENT", "RAW_DNS_RECORDS", "EMAILADDR_GENERIC"):
                texts.append(edata[:4000])
        contacts = filter_institutional_contacts(texts)
        return {
            "invoked": True,
            "modules": validated,
            "exit_code": proc.returncode,
            "discovered_names": sorted(subdomains)[:250],
            "institutional_role_contacts": contacts["institutional_role_contacts"],
            "redacted_personal_email_count": contacts["redacted_personal_or_nonrole_email_count"],
        }
    except Exception as exc:
        return {"invoked": True, "modules": validated, "error": f"{type(exc).__name__}: {exc}"}


def generate_vendor_pra_templates(
    jurisdiction_name: str,
    detected_vendor_ids: Iterable[str],
    arcgis_queries: Iterable[Mapping[str, str]] = (),
) -> list[dict[str, Any]]:
    """Generate human-reviewed W.S. 16-4-202 DRAFT templates matched to detected records vendors."""
    vset = set(detected_vendor_ids)
    drafts: list[dict[str, Any]] = []

    if vset & {"govqa", "nextrequest"}:
        portal_label = "GovQA" if "govqa" in vset else "NextRequest"
        drafts.append({
            "template_class": "portal_meta_audit_govqa_nextrequest",
            "section_id": 7,
            "vendor_basis": sorted(vset & {"govqa", "nextrequest"}),
            "sent_by_this_tool": False,
            "draft_text": (
                f"[DRAFT FOR HUMAN REVIEW — DO NOT AUTO-SEND; NOT LEGAL ADVICE]\n"
                f"To: Public Records Custodian, {jurisdiction_name}\n"
                f"Pursuant to the Wyoming Public Records Act (W.S. 16-4-201 through 16-4-205), "
                f"I request an electronic CSV/Excel export of the {portal_label} public-records intake "
                f"log for the past 12 months containing ONLY non-exempt administrative tracking columns: "
                f"Reference/Ticket ID, Date Submitted, Date Acknowledged, Assigned Department, Current Status, "
                f"Date Closed, and Fee Estimate/Amount Charged (excluding requester personal contact details "
                f"if exempt). Please provide a cost estimate first if fees exceed $25."
            ),
        })

    if vset & {"tyler_itax_eagle", "greenwood_gis"} or True:
        # Standardized CAMA + Check Register applies statewide across all 23 counties (Mirror Layer 1 & Section 2)
        vendor_note = (
            f"Detected stack ({', '.join(sorted(vset & {'tyler_itax_eagle', 'greenwood_gis'}))})"
            if (vset & {"tyler_itax_eagle", "greenwood_gis"})
            else "Statewide DOR CAMA / County Finance baseline"
        )
        drafts.append({
            "template_class": "cama_and_ap_register_csv_export",
            "section_id": 2,
            "vendor_basis": [vendor_note],
            "sent_by_this_tool": False,
            "draft_text": (
                f"[DRAFT FOR HUMAN REVIEW — DO NOT AUTO-SEND; NOT LEGAL ADVICE]\n"
                f"To: Records Custodian / County Clerk & Assessor, {jurisdiction_name}\n"
                f"Pursuant to W.S. 16-4-201 through 16-4-205, please provide in native structured electronic "
                f"CSV format:\n"
                f"  1. Accounts Payable / Warrant Check Register for the prior fiscal year (Vendor Name, "
                f"Check/EFT Date, Fund/GL Account, Invoice/Voucher Number, Amount).\n"
                f"  2. Public CAMA parcel summary roll (Parcel/PIDN, Situs Address, Tax District, Property "
                f"Class/Ag Flag, Year Built, Land Market Value, Improvement Market Value).\n"
                f"Please notify me in advance if estimated fees exceed $25."
            ),
        })

    if vset & {"opengov_viewpoint", "smartgov"}:
        drafts.append({
            "template_class": "permitting_summary_csv_export",
            "section_id": 3,
            "vendor_basis": sorted(vset & {"opengov_viewpoint", "smartgov"}),
            "sent_by_this_tool": False,
            "draft_text": (
                f"[DRAFT FOR HUMAN REVIEW — DO NOT AUTO-SEND; NOT LEGAL ADVICE]\n"
                f"To: Building & Development Services Custodian, {jurisdiction_name}\n"
                f"Pursuant to W.S. 16-4-201 through 16-4-205, please provide a CSV export of commercial "
                f"and industrial building/grading permits issued over the past 24 months (Record ID, Permit "
                f"Type, Address/Parcel, Applicant Business Entity, Date Submitted, Date Issued, Declared "
                f"Valuation, and Permit Fee Paid)."
            ),
        })

    arcgis_list = list(arcgis_queries)
    if ("esri_arcgis" in vset) or arcgis_list:
        drafts.append({
            "template_class": "arcgis_rest_direct_geojson",
            "section_id": 4,
            "vendor_basis": ["esri_arcgis"],
            "sent_by_this_tool": False,
            "arcgis_geojson_endpoints": arcgis_list[:10],
            "draft_text": (
                f"[ZERO-REQUEST PUBLIC GIS INSPECTION NOTE — {jurisdiction_name}]\n"
                f"Public Esri ArcGIS REST endpoints were detected. Verify terms of service and robots.txt, "
                f"then inspect public parcel/zoning layers via bounded read-only `?where=1=1&outFields=*&f=geojson` queries."
            ),
        })

    return drafts


def scan_jurisdiction(
    target: Mapping[str, Any],
    output_dir: Path,
    offline: bool = False,
    delay: float = 2.0,
    timeout: float = 8.0,
    use_spiderfoot: bool = False,
    spiderfoot_modules: str = "sfp_crt,sfp_dnsresolve,sfp_webframework,sfp_email,sfp_accounts",
) -> dict[str, Any]:
    """Run strictly passive OSINT & vendor cartography for a single target entry."""
    validated_modules = validate_spiderfoot_modules(spiderfoot_modules)
    slug = str(target["jurisdiction"])
    domains = list(target.get("candidate_domains", []))[:6]

    domain_reports: list[dict[str, Any]] = []
    all_subdomains: set[str] = set()
    all_mx: set[str] = set()
    all_headers: dict[str, str] = {}
    html_samples: list[str] = []
    contact_inputs: list[str] = []

    for idx, dom in enumerate(domains):
        if offline:
            domain_reports.append({
                "domain": dom,
                "mode": "offline_manifest_only",
                "public_ips": [],
                "mx_records": [],
                "crt_subdomains": [],
                "https_probe": {"reachable": False, "error": "offline mode"},
            })
            continue

        if idx > 0 and delay > 0:
            time.sleep(delay)

        dns_info = _resolve_passive_dns(dom)
        crt_subs, crt_err = _query_crt_sh(dom, timeout=timeout)
        http_info = _polite_https_fingerprint(dom, timeout=timeout)

        all_subdomains.update(crt_subs)
        all_mx.update(dns_info["mx_records"])
        for k, v in http_info.get("headers", {}).items():
            all_headers[f"{dom}:{k}"] = v
        if http_info.get("html_excerpt"):
            html_samples.append(http_info["html_excerpt"])
            contact_inputs.append(http_info["html_excerpt"])

        sf_info = None
        if use_spiderfoot:
            sf_info = _run_optional_spiderfoot_passive(dom, validated_modules)
            all_subdomains.update(sf_info.get("discovered_names", []))
            contact_inputs.extend(sf_info.get("institutional_role_contacts", []))

        domain_reports.append({
            "domain": dom,
            "mode": "live_passive",
            "public_ips": dns_info["public_ips"],
            "mx_records": dns_info["mx_records"],
            "ns_records": dns_info["ns_records"],
            "dns_errors": dns_info["dns_errors"],
            "crt_subdomains_count": len(crt_subs),
            "crt_subdomains": crt_subs[:100],
            "crt_error": crt_err,
            "https_probe": {k: v for k, v in http_info.items() if k != "html_excerpt"},
            "spiderfoot_passive": sf_info,
        })

    fp = fingerprint_saas_vendors(
        subdomains=all_subdomains,
        mx_records=all_mx,
        headers=all_headers,
        html_samples=html_samples,
    )
    contacts = filter_institutional_contacts(contact_inputs)
    vendor_ids = [v["vendor_id"] for v in fp["detected_vendors"]]
    pra_drafts = generate_vendor_pra_templates(
        jurisdiction_name=str(target["name"]),
        detected_vendor_ids=vendor_ids,
        arcgis_queries=fp["arcgis_geojson_queries"],
    )

    result: dict[str, Any] = {
        "jurisdiction": slug,
        "name": target["name"],
        "type": target["type"],
        "county_seat_name": target.get("county_seat_name"),
        "county_seat_slug": target.get("county_seat_slug"),
        "blueprint_domain": target.get("blueprint_domain"),
        "reviewed_official_urls": target.get("reviewed_official_urls", []),
        "verification": target.get("verification", "candidate_unverified"),
        "scanned_at_utc": utc_now(),
        "collection_mode": "offline_manifest_only" if offline else "passive_osint_only",
        "passive_spiderfoot_modules_validated": validated_modules,
        "domains_inspected": domain_reports,
        "discovered_subdomains": sorted(all_subdomains)[:250],
        "detected_vendors": fp["detected_vendors"],
        "arcgis_rest_roots": fp["arcgis_rest_roots"],
        "arcgis_geojson_queries": fp["arcgis_geojson_queries"],
        "institutional_role_contacts": contacts["institutional_role_contacts"],
        "redacted_personal_email_count": contacts["redacted_personal_or_nonrole_email_count"],
        "pra_draft_templates": pra_drafts,
        "mirror_ledgers_available": len(MIRROR_LEDGERS),
        "honesty_statement": (
            "Passive DNS/CT/header/HTML signals are unreviewed infrastructure candidates. "
            "Confirm official government ownership before relying on any domain or submitting records requests."
        ),
    }

    output_dir.mkdir(parents=True, exist_ok=True)
    out_file = output_dir / f"{slug}.json"
    out_file.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    provenance = package_osint_artifact(
        filepath=out_file,
        source_url=f"passive-cartography://{slug}",
        section_tag="Section 7: Passive Infrastructure Cartography",
    )
    result["provenance_sha256"] = provenance["sha256_hash"]
    return result


CARTOGRAPHY_SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS jurisdiction_targets (
    jurisdiction TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    type TEXT NOT NULL,
    county_seat_name TEXT,
    blueprint_domain TEXT,
    verification TEXT NOT NULL,
    collection_mode TEXT NOT NULL,
    reachable_https_domains INTEGER NOT NULL DEFAULT 0,
    subdomain_count INTEGER NOT NULL DEFAULT 0,
    vendor_count INTEGER NOT NULL DEFAULT 0,
    scanned_at_utc TEXT NOT NULL,
    artifact_sha256 TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS discovered_subdomains (
    jurisdiction TEXT NOT NULL REFERENCES jurisdiction_targets(jurisdiction) ON DELETE CASCADE,
    subdomain TEXT NOT NULL,
    PRIMARY KEY (jurisdiction, subdomain)
);

CREATE TABLE IF NOT EXISTS detected_vendors (
    jurisdiction TEXT NOT NULL REFERENCES jurisdiction_targets(jurisdiction) ON DELETE CASCADE,
    vendor_id TEXT NOT NULL,
    label TEXT NOT NULL,
    category TEXT NOT NULL,
    section_id INTEGER NOT NULL,
    evidence_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'candidate_unreviewed',
    PRIMARY KEY (jurisdiction, vendor_id)
);

CREATE TABLE IF NOT EXISTS arcgis_endpoints (
    jurisdiction TEXT NOT NULL REFERENCES jurisdiction_targets(jurisdiction) ON DELETE CASCADE,
    service_url TEXT NOT NULL,
    geojson_query_url TEXT NOT NULL,
    PRIMARY KEY (jurisdiction, service_url)
);

CREATE TABLE IF NOT EXISTS pra_draft_templates (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    jurisdiction TEXT NOT NULL REFERENCES jurisdiction_targets(jurisdiction) ON DELETE CASCADE,
    template_class TEXT NOT NULL,
    section_id INTEGER NOT NULL,
    sent_by_this_tool INTEGER NOT NULL DEFAULT 0 CHECK (sent_by_this_tool = 0),
    draft_text TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mirror_ledger_catalog (
    layer_id INTEGER PRIMARY KEY,
    slug TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    endpoints_json TEXT NOT NULL,
    sections_json TEXT NOT NULL,
    exposes_summary TEXT NOT NULL
);
"""


def consolidate_results(
    input_dir: Path,
    db_out: Path,
    summary_json_out: Path | None = None,
    markdown_out: Path | None = None,
) -> dict[str, Any]:
    """Verify SHA-256 provenance of per-target JSON artifacts and merge into SQLite + Matrix report."""
    artifact_files = sorted(
        p for p in input_dir.rglob("*.json")
        if not p.name.endswith(".provenance.json")
        and p.name not in ("consolidated_cartography.json", "vendor_pra_matrix.json")
    )
    if not artifact_files:
        raise FileNotFoundError(f"No jurisdiction JSON artifacts found in {input_dir}")

    db_out.parent.mkdir(parents=True, exist_ok=True)
    if db_out.exists():
        db_out.unlink()

    conn = sqlite3.connect(db_out)
    rows_summary: list[dict[str, Any]] = []
    try:
        conn.executescript(CARTOGRAPHY_SCHEMA_SQL)
        for layer in MIRROR_LEDGERS:
            conn.execute(
                "INSERT OR REPLACE INTO mirror_ledger_catalog(layer_id, slug, name, endpoints_json, sections_json, exposes_summary) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    layer["layer_id"],
                    layer["slug"],
                    layer["name"],
                    json.dumps(layer["primary_endpoints"]),
                    json.dumps(layer["sections_supported"]),
                    layer["exposes_without_local_pra"],
                ),
            )

        for fpath in artifact_files:
            data = json.loads(fpath.read_text(encoding="utf-8"))
            if "jurisdiction" not in data or "domains_inspected" not in data:
                continue

            sidecar = Path(str(fpath) + ".provenance.json")
            if sidecar.is_file():
                ver = verify_osint_provenance(sidecar, fpath)
                if not ver["verified"]:
                    raise ValueError(f"Provenance hash mismatch for {fpath}: expected {ver['expected_sha256']}, got {ver['actual_sha256']}")
                sha256_hex = ver["actual_sha256"]
            else:
                prov = package_osint_artifact(fpath, f"consolidated://{data['jurisdiction']}", "Section 7")
                sha256_hex = prov["sha256_hash"]

            slug = data["jurisdiction"]
            reachable_count = sum(
                1 for d in data.get("domains_inspected", [])
                if d.get("https_probe", {}).get("reachable")
            )
            subs = data.get("discovered_subdomains", [])
            vendors = data.get("detected_vendors", [])
            arcgis_qs = data.get("arcgis_geojson_queries", [])
            drafts = data.get("pra_draft_templates", [])

            conn.execute(
                "INSERT OR REPLACE INTO jurisdiction_targets("
                "jurisdiction, name, type, county_seat_name, blueprint_domain, verification, "
                "collection_mode, reachable_https_domains, subdomain_count, vendor_count, scanned_at_utc, artifact_sha256"
                ") VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    slug,
                    data["name"],
                    data["type"],
                    data.get("county_seat_name"),
                    data.get("blueprint_domain"),
                    data.get("verification", "candidate_unverified"),
                    data.get("collection_mode", "passive_osint_only"),
                    reachable_count,
                    len(subs),
                    len(vendors),
                    data.get("scanned_at_utc", utc_now()),
                    sha256_hex,
                ),
            )
            for sub in subs:
                conn.execute(
                    "INSERT OR IGNORE INTO discovered_subdomains(jurisdiction, subdomain) VALUES (?, ?)",
                    (slug, sub),
                )
            for v in vendors:
                conn.execute(
                    "INSERT OR REPLACE INTO detected_vendors(jurisdiction, vendor_id, label, category, section_id, evidence_json, status) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        slug,
                        v["vendor_id"],
                        v["label"],
                        v["category"],
                        int(v["section_id"]),
                        json.dumps(v.get("evidence_tokens", [])),
                        v.get("status", "candidate_unreviewed"),
                    ),
                )
            for aq in arcgis_qs:
                conn.execute(
                    "INSERT OR REPLACE INTO arcgis_endpoints(jurisdiction, service_url, geojson_query_url) VALUES (?, ?, ?)",
                    (slug, aq["service_url"], aq["geojson_query_url"]),
                )
            for dr in drafts:
                conn.execute(
                    "INSERT INTO pra_draft_templates(jurisdiction, template_class, section_id, sent_by_this_tool, draft_text) "
                    "VALUES (?, ?, ?, 0, ?)",
                    (slug, dr["template_class"], int(dr["section_id"]), dr["draft_text"]),
                )

            rows_summary.append({
                "jurisdiction": slug,
                "name": data["name"],
                "type": data["type"],
                "verification": data.get("verification", "candidate_unverified"),
                "collection_mode": data.get("collection_mode"),
                "reachable_https_domains": reachable_count,
                "discovered_subdomains": len(subs),
                "detected_vendors": [v["vendor_id"] for v in vendors],
                "arcgis_geojson_endpoints": len(arcgis_qs),
                "pra_draft_count": len(drafts),
                "artifact_sha256": sha256_hex,
            })

        conn.commit()
    finally:
        conn.close()

    rows_summary.sort(key=lambda r: (0 if r["type"] == "state-portal" else 1, r["jurisdiction"]))
    summary = {
        "consolidated_at_utc": utc_now(),
        "database_path": str(db_out),
        "jurisdictions_consolidated": len(rows_summary),
        "mirror_ledgers_indexed": len(MIRROR_LEDGERS),
        "sent_by_this_tool": False,
        "honesty_note": (
            "Passive infrastructure inventory only. Detected vendors carry status='candidate_unreviewed'; "
            "all W.S. 16-4-202 templates are unsent human-review drafts."
        ),
        "jurisdictions": rows_summary,
    }

    if summary_json_out is not None:
        summary_json_out.parent.mkdir(parents=True, exist_ok=True)
        summary_json_out.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")

    if markdown_out is not None:
        md_lines = [
            "# Wyoming Statewide Passive Cartography & Public-Records Matrix",
            "",
            f"- **Consolidated UTC:** `{summary['consolidated_at_utc']}`",
            f"- **Jurisdictions merged:** `{summary['jurisdictions_consolidated']}`",
            f"- **State/Federal Mirror Ledgers indexed:** `{summary['mirror_ledgers_indexed']}`",
            "- **Guardrails:** Passive DNS/CT/HTTPS headers & vendor fingerprinting only; personal emails redacted (`LEGAL.md` §5); all PRA requests are unsent human-reviewed drafts (`LEGAL.md` §4).",
            "",
            "| Jurisdiction | Seat / Scope | Verification | Reachable HTTPS | CT Subdomains | Detected Vendor Candidates | PRA Drafts |",
            "|---|---|---|---:|---:|---|---:|",
        ]
        for r in rows_summary:
            v_str = ", ".join(r["detected_vendors"]) if r["detected_vendors"] else "baseline_cama_mirror"
            md_lines.append(
                f"| `{r['jurisdiction']}` | {r['name']} | `{r['verification']}` | "
                f"{r['reachable_https_domains']} | {r['discovered_subdomains']} | `{v_str}` | {r['pra_draft_count']} |"
            )
        markdown_out.parent.mkdir(parents=True, exist_ok=True)
        markdown_out.write_text("\n".join(md_lines) + "\n", encoding="utf-8")

    package_osint_artifact(
        filepath=db_out,
        source_url="consolidated://wyoming-statewide-records-infrastructure",
        section_tag="Section 7: Consolidated Statewide Records Infrastructure SQLite",
    )
    return summary


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="command", required=True)

    mj = sub.add_parser("matrix-json", help="Emit JSON array of target jurisdiction slugs for GitHub Actions matrix")
    mj.add_argument("--filter", default="", help="Optional comma-separated jurisdiction slug filter")

    sc = sub.add_parser("scan-target", help="Run passive OSINT & vendor fingerprinting for one target")
    sc.add_argument("--jurisdiction", required=True)
    sc.add_argument("--output-dir", default="cartography-results/raw")
    sc.add_argument("--offline", action="store_true", help="Build deterministic manifest + PRA drafts without network")
    sc.add_argument("--use-spiderfoot", action="store_true")
    sc.add_argument("--modules", default="sfp_crt,sfp_dnsresolve,sfp_webframework,sfp_email,sfp_accounts")
    sc.add_argument("--delay", type=float, default=2.0)
    sc.add_argument("--timeout", type=float, default=8.0)

    sa = sub.add_parser("scan-all", help="Sequentially scan all targets (recommended with --offline for local validation)")
    sa.add_argument("--output-dir", default="cartography-results/raw")
    sa.add_argument("--offline", action="store_true")

    co = sub.add_parser("consolidate", help="Merge per-jurisdiction JSON artifacts into SQLite + Vendor PRA Matrix")
    co.add_argument("--input-dir", required=True)
    co.add_argument("--db", default="cartography-results/wyoming_statewide_records_infrastructure.db")
    co.add_argument("--summary-json", default="cartography-results/consolidated_cartography.json")
    co.add_argument("--markdown", default="cartography-results/vendor_pra_matrix.md")

    args = ap.parse_args(argv)
    manifest = load_targets()
    by_slug = {t["jurisdiction"]: t for t in manifest["targets"]}

    if args.command == "matrix-json":
        wanted = {s.strip() for s in args.filter.split(",") if s.strip()}
        slugs = [s for s in by_slug if not wanted or s in wanted]
        if not slugs:
            ap.error("No matching jurisdiction slugs found in wyoming/targets.json")
        print(json.dumps(slugs))
        return 0

    if args.command == "scan-target":
        if args.jurisdiction not in by_slug:
            ap.error(f"Unknown jurisdiction '{args.jurisdiction}'. Valid: {', '.join(sorted(by_slug))}")
        res = scan_jurisdiction(
            target=by_slug[args.jurisdiction],
            output_dir=Path(args.output_dir),
            offline=args.offline,
            delay=args.delay,
            timeout=args.timeout,
            use_spiderfoot=args.use_spiderfoot,
            spiderfoot_modules=args.modules,
        )
        print(json.dumps({
            "jurisdiction": res["jurisdiction"],
            "detected_vendors": [v["vendor_id"] for v in res["detected_vendors"]],
            "discovered_subdomains_count": len(res["discovered_subdomains"]),
            "provenance_sha256": res["provenance_sha256"],
        }, indent=2))
        return 0

    if args.command == "scan-all":
        out_dir = Path(args.output_dir)
        for t in manifest["targets"]:
            scan_jurisdiction(t, output_dir=out_dir, offline=args.offline)
        print(json.dumps({"scanned": len(manifest["targets"]), "output_dir": str(out_dir)}, indent=2))
        return 0

    if args.command == "consolidate":
        summary = consolidate_results(
            input_dir=Path(args.input_dir),
            db_out=Path(args.db),
            summary_json_out=Path(args.summary_json) if args.summary_json else None,
            markdown_out=Path(args.markdown) if args.markdown else None,
        )
        print(json.dumps({
            "jurisdictions_consolidated": summary["jurisdictions_consolidated"],
            "database_path": summary["database_path"],
        }, indent=2))
        return 0

    return 2


if __name__ == "__main__":
    raise SystemExit(main())
