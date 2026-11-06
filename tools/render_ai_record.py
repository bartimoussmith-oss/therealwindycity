#!/usr/bin/env python3
"""render_ai_record.py - turn ai-record/ (Markdown) into a static site.

Every .md becomes a plain, JavaScript-free .html page AND is copied as .md,
so both people and AI fetchers can read it. Adds robots.txt (welcomes AI
crawlers), sitemap.xml, llms.txt, .nojekyll, and 404.html.

    python3 tools/render_ai_record.py --src ai-record --out _site
"""
import argparse, html, json, os, re, shutil, sys
from pathlib import Path
from datetime import datetime, timezone

SITE = "https://bartimoussmith-oss.github.io/therealwindycity/"
NAME = "Cheyenne Public Meetings Record"

CSS = """body{margin:0;font:17px/1.6 Georgia,'Times New Roman',serif;color:#1b1b1b;background:#fbf8f1}
main{max-width:980px;margin:0 auto;padding:18px 20px 60px}
header.site{background:#1b1b1b;color:#f4ecd8;padding:10px 20px;font:15px/1.4 system-ui,sans-serif}
header.site a{color:#ffd93b;text-decoration:none;margin-right:16px}
h1{font-size:1.9em;line-height:1.2;margin:.6em 0 .3em}h2{margin-top:1.6em;border-bottom:2px solid #d8cfbc}
h3{margin-top:1.4em;font-size:1.05em;color:#6b3a2b}
a{color:#8a2f1f}table{border-collapse:collapse;width:100%;font-size:.92em;margin:1em 0}
th,td{border:1px solid #d8cfbc;padding:5px 8px;vertical-align:top;text-align:left}th{background:#efe6d2}
pre{white-space:pre-wrap;word-wrap:break-word;background:#fff;border:1px solid #e2dacb;padding:12px;font:14px/1.5 ui-monospace,Menlo,Consolas,monospace}
code{font-family:ui-monospace,Menlo,Consolas,monospace;font-size:.92em}
footer{margin-top:40px;font:14px/1.5 system-ui,sans-serif;color:#555}"""

TEMPLATE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title} | {name}</title>
<meta name="description" content="{desc}">
<meta name="robots" content="index,follow,max-snippet:-1">
<link rel="canonical" href="{canonical}">
<link rel="alternate" type="text/markdown" href="{md_url}">
<meta property="og:title" content="{title}"><meta property="og:description" content="{desc}"><meta property="og:type" content="article"><meta property="og:url" content="{canonical}">
<script type="application/ld+json">{jsonld}</script>
<style>{css}{prov_css}</style></head>
<body><header class="site"><a href="{root}index.html"><b>{name}</b></a><a href="{root}provenance/master.html">Guide &amp; films</a><a href="{root}provenance/granicus.html">City archive vs this</a><a href="{root}indexes/keywords.html">Keyword index</a><a href="{root}topics/corrections.html">Corrections</a><a href="{root}llms.txt">llms.txt</a><a href="{md_rel}">View as Markdown</a></header>
<main>
{body}
{prov}
<footer>Plain-text mirror of public records of the City of Cheyenne, Wyoming. Not an official city website. Original files: <a href="https://github.com/therealwindycity">github.com/therealwindycity</a>. Markdown source of this page: <a href="{md_rel}">{md_name}</a>.</footer>
</main></body></html>
"""

ROBOTS = """# Everyone, including AI crawlers and assistants, is welcome to read and cite this public record.
User-agent: *
Allow: /

User-agent: GPTBot
Allow: /
User-agent: OAI-SearchBot
Allow: /
User-agent: ChatGPT-User
Allow: /
User-agent: ClaudeBot
Allow: /
User-agent: Claude-User
Allow: /
User-agent: Claude-SearchBot
Allow: /
User-agent: anthropic-ai
Allow: /
User-agent: PerplexityBot
Allow: /
User-agent: Perplexity-User
Allow: /
User-agent: Google-Extended
Allow: /
User-agent: Googlebot
Allow: /
User-agent: Bingbot
Allow: /
User-agent: Applebot-Extended
Allow: /
User-agent: CCBot
Allow: /
User-agent: meta-externalagent
Allow: /
User-agent: DuckAssistBot
Allow: /

Sitemap: {site}sitemap.xml
"""


def slugify(value, sep="-"):
    return re.sub(r"[^A-Za-z0-9]+", "-", value).strip("-").lower()


def strip_md(s):
    s = re.sub(r"\[([^\]]*)\]\([^)]*\)", r"\1", s)
    s = re.sub(r"[*_`#>|\\]", "", s)
    return re.sub(r"\s+", " ", s).strip()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default="ai-record")
    ap.add_argument("--out", default="_site")
    ap.add_argument("--extra", action="append", default=[], help="src=dest file to copy into the site")
    ap.add_argument("--no-provenance", action="store_true",
                    help="skip the provenance block (origin links + film cues) on every page")
    ap.add_argument("--provenance-root", default=".", help="repo root holding data/out/provenance-ledger.json")
    a = ap.parse_args()
    import markdown
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    try:
        from provenance import site as prov_site
    except Exception as exc:  # the site must still build without the ledger package
        print(f"  provenance: unavailable ({exc})", file=sys.stderr)
        prov_site = None
    ledger = None if (a.no_provenance or prov_site is None) else prov_site.load(Path(a.provenance_root))
    if ledger:
        print(f"  provenance: {ledger['totals']['data']:,} datums, "
              f"{ledger['totals']['with_link']:,} linked, {ledger['totals']['with_cue']:,} cued",
              file=sys.stderr)
    if os.path.exists(a.out): shutil.rmtree(a.out)
    os.makedirs(a.out)
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"],
                           extension_configs={"toc": {"slugify": slugify}})
    link_re = re.compile(r'href="(?!https?:|mailto:|#)([^"#]*\.md)(#[^"]*)?"')
    page_rel_of: dict[str, str] = {}

    def fix_link(m):
        path, anchor = m.group(1), m.group(2) or ""
        path = path[:-9] + "index.html" if path.endswith("README.md") else path[:-3] + ".html"
        return f'href="{path}{anchor}"'

    urls = []
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for root, _, files in os.walk(a.src):
        for f in sorted(files):
            src = os.path.join(root, f)
            rel = os.path.relpath(src, a.src).replace(os.sep, "/")
            dst_dir = os.path.join(a.out, os.path.dirname(rel))
            os.makedirs(dst_dir, exist_ok=True)
            if not f.endswith(".md"):
                shutil.copy2(src, os.path.join(a.out, rel))
                continue
            text = open(src, encoding="utf-8").read()
            shutil.copy2(src, os.path.join(a.out, rel))       # .md stays fetchable
            html_rel = rel[:-3] + ".html"
            if f == "README.md":
                html_rel = os.path.join(os.path.dirname(rel), "index.html").replace(os.sep, "/").lstrip("/")
            md.reset()
            body = md.convert(text)
            body = link_re.sub(fix_link, body)
            title_m = re.search(r"^#\s+(.+)$", text, re.M)
            title = strip_md(title_m.group(1)) if title_m else rel
            desc_m = re.search(r"^\*(.+?)\*\s*$", text, re.M)
            desc = strip_md(desc_m.group(1))[:300] if desc_m else title
            depth = html_rel.count("/")
            root_rel = "../" * depth
            canonical = SITE + html_rel
            jsonld = {"@context": "https://schema.org", "@type": "WebPage", "name": title, "description": desc,
                      "url": canonical, "inLanguage": "en", "isAccessibleForFree": True,
                      "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE},
                      "about": {"@type": "Place", "name": "Cheyenne, Wyoming"}}
            dm = re.search(r"(\d{4}-\d{2}-\d{2})", rel)
            if dm and rel.startswith(("meetings/", "documents/")):
                jsonld["temporalCoverage"] = dm.group(1)
            prov = prov_site.block(html_rel, ledger, root_rel) if ledger else ""
            page_rel_of[rel] = html_rel
            page = TEMPLATE.format(title=html.escape(title), name=NAME, desc=html.escape(desc), canonical=canonical,
                                   md_url=SITE + rel, md_rel=os.path.basename(rel), md_name=html.escape(rel),
                                   jsonld=json.dumps(jsonld).replace("</", "<\\/"), css=CSS, root=root_rel, body=body,
                                   prov=prov, prov_css=prov_site.CSS if prov else "")
            with open(os.path.join(a.out, html_rel), "w", encoding="utf-8") as fh:
                fh.write(("<!-- provenance: every figure on this page carries an origin link and a "
                          "film cue; see /provenance/ -->\n" if prov else "") + page)
            urls.append(canonical)
    if ledger and prov_site is not None:
        write_provenance_site(a, ledger, prov_site, urls, page_rel_of)
    for spec in a.extra:
        s, d = spec.split("=", 1)
        if os.path.exists(s):
            os.makedirs(os.path.dirname(os.path.join(a.out, d)) or a.out, exist_ok=True)
            shutil.copy2(s, os.path.join(a.out, d))
    open(os.path.join(a.out, "robots.txt"), "w").write(ROBOTS.format(site=SITE))
    open(os.path.join(a.out, ".nojekyll"), "w").write("")
    urls.sort(key=lambda u: (u.count("/"), u))
    with open(os.path.join(a.out, "sitemap.xml"), "w") as fh:
        fh.write('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n')
        for u in urls:
            fh.write(f"<url><loc>{html.escape(u)}</loc><lastmod>{now}</lastmod></url>\n")
        fh.write("</urlset>\n")
    with open(os.path.join(a.out, "404.html"), "w") as fh:
        fh.write(f'<!doctype html><meta charset="utf-8"><title>Not found</title><p>Page not found. Start at <a href="{SITE}">{SITE}</a> or read <a href="{SITE}llms.txt">llms.txt</a>.</p>')
    print(f"rendered {len(urls)} pages into {a.out}")


def write_provenance_site(a, ledger, prov_site, urls, page_rel_of):
    """Write /provenance/ and make sure every clip a cue points at exists in the site."""
    pdir = os.path.join(a.out, "provenance")
    os.makedirs(pdir, exist_ok=True)
    root_rel = "../"
    ctx = {"rel": "provenance/index.html", "title": "Provenance and cue sheet",
           "desc": "Every figure, origin link, and film cue in this record.",
           "pages": page_rel_of}
    body = prov_site.page(ledger, root_rel, ctx)
    canonical = SITE + "provenance/index.html"
    jsonld = {"@context": "https://schema.org", "@type": "WebPage",
              "name": "Provenance — every number and how it was collected",
              "description": "Every figure on this site, the public page it came from, the clicks to "
                             "fetch it, and a film cue showing that fetch.",
              "url": canonical, "inLanguage": "en", "isAccessibleForFree": True,
              "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE}}
    html_page = TEMPLATE.format(title=ctx["title"], name=NAME,
                                desc=ctx["desc"],
                                canonical=canonical, md_url=SITE + "provenance/ledger.md",
                                md_rel="ledger.md", md_name="provenance/ledger.md",
                                jsonld=json.dumps(jsonld).replace("</", "<\\/"), css=CSS,
                                root=root_rel, body=body, prov="", prov_css=prov_site.CSS)
    with open(os.path.join(pdir, "index.html"), "w", encoding="utf-8") as fh:
        fh.write(html_page)
    urls.append(canonical)

    # the master guide: what everything is, the films, and how to check a number
    try:
        from provenance import guide as prov_guide
        facts = prov_guide.facts(Path(a.provenance_root))
        guide_body = prov_guide.html(ledger, root_rel, facts)
    except Exception as exc:  # the site must still build without the guide
        print(f"  provenance: guide skipped ({exc})", file=sys.stderr)
        guide_body = ""
    if guide_body:
        gcanon = SITE + "provenance/master.html"
        gjson = {"@context": "https://schema.org", "@type": "WebPage",
                 "name": "The provenance guide — everything in this archive, and how it was collected",
                 "description": "One page for the whole record: the films, the films' chapters, "
                                "the ledger, and how to check any number yourself.",
                 "url": gcanon, "inLanguage": "en", "isAccessibleForFree": True,
                 "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE}}
        gpage = TEMPLATE.format(title="The provenance guide", name=NAME,
                                desc="Everything in this archive, the films that show how it was "
                                     "collected, and how to check any number yourself.",
                                canonical=gcanon, md_url=SITE + "provenance/guide.md",
                                md_rel="guide.md", md_name="provenance/guide.md",
                                jsonld=json.dumps(gjson).replace("</", "<\\/"),
                                css=CSS, root=root_rel, body=guide_body,
                                prov="", prov_css=prov_site.CSS + prov_guide.GUIDE_CSS)
        with open(os.path.join(pdir, "master.html"), "w", encoding="utf-8") as fh:
            fh.write(gpage)
        urls.append(gcanon)

    # the comparison: the city's own Granicus portal against this archive
    try:
        from provenance import compare as prov_compare
        cfacts = prov_compare.facts(Path(a.provenance_root))
        cfacts["datums"] = (ledger.get("totals") or {}).get("data", 0)
        cbody = prov_compare.html(root_rel, cfacts)
    except Exception as exc:  # the site must still build without the comparison
        print(f"  provenance: comparison skipped ({exc})", file=sys.stderr)
        cbody = ""
    if cbody:
        ccanon = SITE + "provenance/granicus.html"
        cjson = {"@context": "https://schema.org", "@type": "WebPage",
                 "name": "The city's own archive, and this one — what differs",
                 "description": "The City of Cheyenne's Granicus portal compared with this "
                                "archive: what each holds, what only the portal has, what only "
                                "this archive has, and where this archive is behind.",
                 "url": ccanon, "inLanguage": "en", "isAccessibleForFree": True,
                 "isPartOf": {"@type": "WebSite", "name": NAME, "url": SITE}}
        cpage = TEMPLATE.format(title="The city's archive, and this one",
                                name=NAME,
                                desc="The City of Cheyenne's own Granicus portal compared with "
                                     "this archive, figure by figure.",
                                canonical=ccanon, md_url=SITE + "provenance/granicus.md",
                                md_rel="granicus.md", md_name="provenance/granicus.md",
                                jsonld=json.dumps(cjson).replace("</", "<\\/"),
                                css=CSS, root=root_rel, body=cbody,
                                prov="", prov_css=prov_site.CSS + prov_compare.COMPARE_CSS)
        with open(os.path.join(pdir, "granicus.html"), "w", encoding="utf-8") as fh:
            fh.write(cpage)
        urls.append(ccanon)

    copied = 0
    src_root = Path(a.provenance_root)

    def want(rel_src: str) -> None:
        nonlocal copied
        if not rel_src:
            return
        src = src_root / rel_src
        if not src.exists():
            print(f"  provenance: MISSING asset {rel_src}", file=sys.stderr)
            return
        dst = os.path.join(a.out, rel_src)
        if os.path.exists(dst):
            return
        os.makedirs(os.path.dirname(dst) or a.out, exist_ok=True)
        shutil.copy2(src, dst)
        copied += 1

    film = ledger.get("film", {})
    for key in ("master", "showcase", "timelapse"):
        want(film.get(key, ""))
    for poster in ("video/provenance-timelapse-poster.jpg", "video/provenance-showcase.jpg",
                   "video/provenance-manual-run.jpg"):
        want(poster)
    for d in ledger.get("data", []):
        cue = d.get("cue") or {}
        want(cue.get("src", ""))
        if cue.get("src"):
            want(cue["src"].rsplit(".", 1)[0] + ".jpg")
    tag = ("<!-- provenance: cue sheet generated from the repository. "
           "Every figure on this site carries an origin link and a film cue. -->\n")
    head = "<!-- provenance: every figure below carries an origin link and a film cue -->\n"
    src_guide = src_root / "data" / "out" / "PROVENANCE-GUIDE.md"
    if src_guide.exists():
        shutil.copy2(src_guide, os.path.join(pdir, "guide.md"))
    src_cmp = src_root / "data" / "out" / "GRANICUS-VS-THIS-ARCHIVE.md"
    if src_cmp.exists():
        shutil.copy2(src_cmp, os.path.join(pdir, "granicus.md"))
    src_md = src_root / "data" / "out" / "PROVENANCE-LEDGER.md"
    if src_md.exists():
        shutil.copy2(src_md, os.path.join(pdir, "ledger.md"))
    src_js = src_root / "data" / "out" / "provenance-ledger.json"
    if src_js.exists():
        shutil.copy2(src_js, os.path.join(pdir, "ledger.json"))
    print(f"  provenance: /provenance/ written, {copied} film assets copied", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())
