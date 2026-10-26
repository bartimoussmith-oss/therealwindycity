#!/usr/bin/env python3
"""Validate and copy the isolated Media Studio into an existing Pages artifact.
Run after the normal site renderer: python tools/publish_media_studio.py --out _site
This helper does not deploy anything and is not yet wired into the Pages workflow.
"""
import argparse
import json
from pathlib import Path
import shutil

def validate(src):
    data = json.loads((src / 'drops.json').read_text(encoding='utf-8'))
    assert data['schema'] == 'media-drops-v1'
    sources = {s['id']: s for s in data['sources']}
    ids = set()
    for d in data['drops']:
        assert d['id'] not in ids
        ids.add(d['id'])
        assert d['source_id'] in sources
        assert all(d.get(k) for k in ('date', 'title', 'finding', 'significance', 'question', 'limits', 'locator', 'excerpt'))
        assert sources[d['source_id']]['url'].startswith('https://github.com/')
    for name in ('index.html', 'builder.html', 'review.html', 'studio.js', 'studio.css'):
        assert (src / name).is_file(), name
    return data

def main():
    p = argparse.ArgumentParser()
    p.add_argument('--out', default='_site')
    p.add_argument('--check-only', action='store_true')
    a = p.parse_args()
    src = Path(__file__).resolve().parents[1] / 'civic_atlas' / 'media'
    data = validate(src)
    if not a.check_only:
        out = Path(a.out)
        if not (out / 'index.html').is_file():
            raise SystemExit('Refusing to create a replacement site: render the existing site first.')
        shutil.copytree(src, out / 'media', dirs_exist_ok=True)
    print(f'Validated {len(data["drops"])} historical drafts; no deployment performed.')

if __name__ == '__main__':
    main()
