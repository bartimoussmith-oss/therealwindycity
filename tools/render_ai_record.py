#!/usr/bin/env python3
"""render_ai_record.py - turn ai-record/ (Markdown) into a static site.

Every .md becomes a plain, JavaScript-free .html page AND is copied as .md,
so both people and AI fetchers can read it. Adds robots.txt (welcomes AI
crawlers), sitemap.xml, llms.txt, .nojekyll, and 404.html.

    python3 tools/render_ai_record.py --src ai-record --out _site
"""
import argparse, html, json, os, re, shutil, sys
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
<style>{css}</style></head>
<body><header class="site"><a href="{root}index.html"><b>{name}</b></a><a href="{root}indexes/keywords.html">Keyword index</a><a href="{root}topics/corrections.html">Corrections</a><a href="{root}llms.txt">llms.txt</a><a href="{md_rel}">View as Markdown</a></header>
<main>
{body}
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
    a = ap.parse_args()
    import markdown
    if os.path.exists(a.out): shutil.rmtree(a.out)
    os.makedirs(a.out)
    md = markdown.Markdown(extensions=["tables", "fenced_code", "toc", "sane_lists"],
                           extension_configs={"toc": {"slugify": slugify}})
    link_re = re.compile(r'href="(?!https?:|mailto:|#)([^"#]*\.md)(#[^"]*)?"')

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
            page = TEMPLATE.format(title=html.escape(title), name=NAME, desc=html.escape(desc), canonical=canonical,
                                   md_url=SITE + rel, md_rel=os.path.basename(rel), md_name=html.escape(rel),
                                   jsonld=json.dumps(jsonld).replace("</", "<\\/"), css=CSS, root=root_rel, body=body)
            with open(os.path.join(a.out, html_rel), "w", encoding="utf-8") as fh:
                fh.write(page)
            urls.append(canonical)
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


if __name__ == "__main__":
    sys.exit(main())
