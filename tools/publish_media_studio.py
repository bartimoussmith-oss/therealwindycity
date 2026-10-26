#!/usr/bin/env python3
"""Validate and add browser-readable media packages to the existing site."""
import argparse
from html import escape
import io
import json
from pathlib import Path
import re
import shutil
from urllib.parse import urlparse
import zipfile

STYLE = 'body{font:18px/1.65 system-ui,sans-serif;color:#182333;background:#fafbfc;margin:0}main{max-width:880px;margin:auto;padding:28px}nav{display:flex;gap:18px;flex-wrap:wrap}a{color:#075b78}article,section{border:1px solid #bac6d2;border-radius:10px;padding:22px;margin:20px 0}h1{line-height:1.2}.notice{background:#fff3ce;padding:14px}pre{white-space:pre-wrap;overflow-wrap:anywhere;font:inherit}small{display:block}@media print{nav,.downloads{display:none}body{background:white}section{break-inside:avoid}}'

def page(title, body):
    return '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>' + escape(title) + ' | The Real Windy City</title><style>' + STYLE + '</style></head><body><main>' + body + '</main></body></html>'

def safe_url(value):
    if urlparse(value).scheme != 'https' or not urlparse(value).netloc:
        raise ValueError('Source URL must be absolute HTTPS')
    return escape(value, quote=True)

def validate(src):
    data = json.loads((src / 'drops.json').read_text(encoding='utf-8'))
    if data.get('schema') != 'media-drops-v1':
        raise ValueError('Invalid schema')
    sources = {s['id']: s for s in data['sources']}
    if len(sources) != len(data['sources']):
        raise ValueError('Duplicate source IDs')
    ids = set()
    for d in data['drops']:
        if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', d['id']) or d['id'] in ids:
            raise ValueError('Unsafe or duplicate drop ID')
        ids.add(d['id'])
        if d['source_id'] not in sources:
            raise ValueError('Unknown source')
        if not all(d.get(k) for k in ('date','title','finding','significance','question','limits','locator','excerpt')):
            raise ValueError('Incomplete drop')
        safe_url(sources[d['source_id']]['url'])
    for name in ('index.html','builder.html','review.html','studio.js','studio.css'):
        if not (src / name).is_file():
            raise ValueError('Missing asset: ' + name)
    return data

def package_files(d, s, coverage):
    title, finding = d['title'], d['finding']
    source = f"Source: {s['url']}\nLocator: {d['locator']}\nSource version (Git blob): {s['git_blob_sha']}\nSource note: {s['note']}"
    story = f"ARCHIVE REWIND | {d['date']} | EDITORIAL DRAFT\n{title}\n\n{finding}\n\nWHY IT MATTERS\n{d['significance']}\n\nFOLLOW-UP QUESTION\n{d['question']}\n\nLIMITATIONS\n{d['limits']}\n\n{source}\n\nCoverage: {coverage}"
    cards = [title, finding, d['significance'], d['question'], d['limits'], source]
    assets = {
        'article.txt': story,
        'newsletter.txt': f"Subject: Archive rewind: {title}\n\n{story}",
        'youtube-description.txt': f"HISTORICAL EXPLAINER DRAFT — source video not rendered\n\n{story}\n\nAdd verified video timestamps only after reviewing the original recording.",
        'social-caption.txt': f"ARCHIVE REWIND ({d['date']}): {title}\n\n{finding}\n\n{d['limits']}\n\nRead the source: {s['url']}",
        'video-script.txt': f"SCRIPT ONLY — NO VIDEO RENDERED\nOpening: {title} ({d['date']})\nNarration: {finding}\nContext: {d['significance']}\nClosing question: {d['question']}\nOn-screen qualification: {d['limits']}\n{source}",
        'carousel.txt': '\n\n'.join(f'{i+1}. {card}' for i, card in enumerate(cards)),
        'source-sheet.txt': source + '\nSupporting extracted-text fragment (OCR whitespace may differ): ' + d['excerpt'] + '\nNot a verified audio quotation. Original records and later developments require review.'
    }
    payload = {'schema':'media-package-v1','status':'historical_editorial_draft','drop':d,'source':s,'coverage':coverage,'assets':assets.copy(),'video_rendered':False,'images_rendered':False}
    assets['package.json'] = json.dumps(payload, ensure_ascii=False, indent=2)
    intro = '<nav><a href="../index.html">All browser packages</a><a href="../../index.html">Media Studio</a></nav>'
    body = intro + '<article><p class="notice">HISTORICAL REWIND / EDITORIAL DRAFT / Event date: ' + escape(d['date']) + '</p><h1>' + escape(title) + '</h1><p>' + escape(finding) + '</p>'
    for heading, text in [('Why it matters',d['significance']),('Follow-up question',d['question']),('Limitations',d['limits'])]:
        body += '<h2>' + heading + '</h2><p>' + escape(text) + '</p>'
    body += '<h2>Inspect the source</h2><p><a href="' + safe_url(s['url']) + '">Repository-held extracted proceedings</a></p><p>' + escape(d['locator']) + '</p><p>' + escape(s['note']) + '</p><small>Git blob: ' + escape(s['git_blob_sha']) + '</small><p>' + escape(coverage) + '</p></article>'
    body += '<section><h2>Browser carousel</h2><p>Readable cards, not rendered image files.</p>'
    for i, card in enumerate(cards):
        body += '<article><h3>Card ' + str(i+1) + '</h3><p>' + escape(card) + '</p></article>'
    body += '</section>'
    for name, text in assets.items():
        if name.endswith('.txt'):
            body += '<section><h2>' + escape(name.replace('.txt','').replace('-',' ').title()) + '</h2><pre>' + escape(text) + '</pre></section>'
    body += '<section class="downloads"><h2>Downloads</h2><ul>'
    for name in assets:
        body += '<li><a download href="' + name + '">' + escape(name) + '</a></li>'
    body += '<li><a download href="package.zip">Complete portable package ZIP</a></li></ul></section><p>Use your browser Print command for a printable copy. No video, audio, or image assets have been rendered. No automatic social posting.</p>'
    assets['index.html'] = page(title, body)
    portable = assets['index.html'].replace(intro, '<p>The Real Windy City / Portable historical media package</p>')
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as z:
        for name, text in assets.items():
            z.writestr(name, portable if name == 'index.html' else text)
    assets['package.zip'] = buffer.getvalue()
    return assets

def publish(src, out):
    data = validate(src)
    if not (out / 'index.html').is_file():
        raise ValueError('Render the existing site first; refusing replacement site')
    shutil.copytree(src, out / 'media', dirs_exist_ok=True)
    packages = out / 'media' / 'packages'
    packages.mkdir(parents=True, exist_ok=True)
    sources = {s['id']:s for s in data['sources']}
    listing = '<nav><a href="../index.html">Media Studio</a><a href="../builder.html">Drop Builder</a></nav><h1>Historical media packages</h1><p class="notice">Editorial drafts, not breaking news. Read articles, source sheets, carousel cards and platform-independent copy directly in your browser. No social account required.</p><p>' + escape(data['coverage']) + '</p>'
    manifest = []
    for d in data['drops']:
        target = packages / d['id']
        target.mkdir(exist_ok=True)
        for name, content in package_files(d, sources[d['source_id']], data['coverage']).items():
            (target / name).write_bytes(content if isinstance(content, bytes) else content.encode('utf-8'))
        listing += '<article><p>' + escape(d['date']) + ' / HISTORICAL DRAFT</p><h2><a href="' + d['id'] + '/index.html">' + escape(d['title']) + '</a></h2><p>' + escape(d['finding']) + '</p></article>'
        manifest.append({'id':d['id'],'article':d['id']+'/index.html','package':d['id']+'/package.zip','status':'historical_editorial_draft'})
    (packages / 'index.html').write_text(page('Historical media packages', listing), encoding='utf-8')
    (packages / 'manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
    return manifest

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out',default='_site')
    p.add_argument('--check-only',action='store_true')
    a = p.parse_args()
    src = Path(__file__).resolve().parents[1] / 'civic_atlas' / 'media'
    data = validate(src)
    if not a.check_only:
        publish(src,Path(a.out))
    print(f'Validated {len(data["drops"])} historical drafts; no deployment performed.')

if __name__ == '__main__':
    main()
