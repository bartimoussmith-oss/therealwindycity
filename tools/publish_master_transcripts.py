import gzip, hashlib, html, json
from pathlib import Path

def build(out, master=None):
    out = Path(out)
    master = Path(master or Path(__file__).resolve().parents[1] / 'drive-import/master_meetings_database.json.gz')
    with gzip.open(master, 'rb') as handle:
        raw = handle.read(100_000_001)
    if len(raw) > 100_000_000:
        raise ValueError('Caption master exceeds publication limit')
    data = json.loads(raw)
    if not isinstance(data, list):
        raise ValueError('Expected caption record list')
    folder = out / 'transcripts-master'
    folder.mkdir(parents=True, exist_ok=True)
    rows, written = [], set()
    for i, record in enumerate(data):
        text = '\n'.join(str(t.get('text') or '') for t in (record.get('turns') or []) if isinstance(t, dict)).strip()
        if not text:
            continue
        digest = hashlib.sha256(text.encode()).hexdigest()
        title, date, category = str(record.get('title') or 'Untitled'), str(record.get('date') or 'Unknown'), str(record.get('category') or 'Unclassified')
        rows.append(dict(title=title, date=date, category=category, master_record=i, text_sha256=digest, file=digest+'.html'))
        if digest in written:
            continue
        written.add(digest)
        page = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>'+html.escape(title)+'</title><body><main style="max-width:960px;margin:auto;padding:20px;font:17px/1.6 system-ui"><a href="index.html">All master transcripts</a><h1>'+html.escape(title)+'</h1><p>'+html.escape(date+' | '+category)+'</p><p>Caption-derived research text, not official minutes or independently verified speech. Dates, speaker labels and full recording coverage require verification. This page uses the first master record carrying this exact text; other representations remain in the index.</p><p>Source: public GitHub drive-import/master_meetings_database.json.gz; record '+str(i)+'. Text SHA-256: '+digest+'</p><a href="'+digest+'.txt" download>Download text</a><pre style="white-space:pre-wrap;overflow-wrap:anywhere;font:inherit">'+html.escape(text)+'</pre></main></body></html>'
        (folder/(digest+'.html')).write_text(page, encoding='utf-8')
        (folder/(digest+'.txt')).write_text(text, encoding='utf-8')
    if not rows:
        raise ValueError('Refusing empty caption publication')
    summary = dict(master_sha256=hashlib.sha256(raw).hexdigest(), master_records=len(data), published_representations=len(rows), unique_exact_texts=len(written), scope='Public caption master only; not complete historical ASR coverage')
    (folder/'index.json').write_text(json.dumps(dict(summary=summary, records=rows), ensure_ascii=False), encoding='utf-8')
    links = ''.join('<li><a href="'+r['file']+'">'+html.escape(r['date']+' | '+r['category']+' | '+r['title'])+'</a> <small>master record '+str(r['master_record'])+'</small></li>' for r in sorted(rows,key=lambda r:(r['date'],r['title']),reverse=True))
    index = '<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Master Caption Transcript Library</title><body><main style="max-width:1100px;margin:auto;padding:20px;font:17px/1.6 system-ui"><a href="../index.html">Archive home</a><h1>Master Caption Transcript Library</h1><p>'+str(len(rows))+' representations; '+str(len(written))+' unique exact texts. Repeated representations share one text page.</p><p>Caption-derived text, not certified transcripts. Dates and attribution require verification. This is not a complete meeting inventory or live collection status.</p><label>Filter dates, titles and bodies <input id="q" type="search"></label><p id="count" role="status"></p><ul>'+links+'</ul><a href="index.json">Machine-readable index and source hash</a><script>const q=document.getElementById("q"),items=[...document.querySelectorAll("li")];q.addEventListener("input",()=>{let n=0;for(const item of items){item.hidden=!item.textContent.toLowerCase().includes(q.value.toLowerCase());if(!item.hidden)n++;}document.getElementById("count").textContent=n+" matching representations";});</script></main></body></html>'
    (folder/'index.html').write_text(index,encoding='utf-8')
    for relative in ('index.html','indexes/caption-transcripts.html'):
        path=out/relative
        if path.is_file():
            existing=path.read_text(encoding='utf-8')
            link=('../' if relative.startswith('indexes/') else '')+'transcripts-master/index.html'
            nav='<nav aria-label="Master caption archive"><a href="'+link+'">Browse the master caption transcript library</a></nav>'
            if nav not in existing:
                path.write_text(existing.replace('</body>',nav+'</body>') if '</body>' in existing else existing+nav,encoding='utf-8')
    assert all((folder/r['file']).is_file() for r in rows)
    return ['transcripts-master/index.html']+['transcripts-master/'+d+'.html' for d in sorted(written)]
