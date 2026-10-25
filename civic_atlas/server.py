"""Read-only Civic Atlas. Run: python -m civic_atlas.server --port 8080."""
import argparse
import hashlib
import json
import mimetypes
import re
from html.parser import HTMLParser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse, parse_qs, unquote

ROOT = Path(__file__).resolve().parents[1]
WEB = Path(__file__).parent
TOPICS = ['Data center', 'Cox Ranch', 'Highlands', 'Water', 'Annexation', 'Zoning', 'Public comment', 'Budget', 'Ordinance', 'Transit']

def terms(text):
    return set(re.findall(r'[a-z0-9]{3,}', text.lower())) - {'the','and','for','that','this','with','from','are','was','meeting','city','cheyenne','2026','2025','2024','have','not','but','you','your'}

class AgendaParser(HTMLParser):
    """Extract source agenda links without executing archived HTML."""
    def __init__(self):
        super().__init__(); self.items=[]; self.current=None
    def handle_starttag(self, tag, attrs):
        attrs=dict(attrs)
        if tag=='a' and 'Agenda' in attrs.get('class','').split():
            self.current={'title':'','url':attrs.get('href','')}
    def handle_data(self,data):
        if self.current is not None:self.current['title']+=data
    def handle_endtag(self,tag):
        if tag=='a' and self.current is not None:
            self.current['title']=self.current['title'].strip()
            self.items.append(self.current);self.current=None

class Corpus:
    def __init__(self, root=ROOT):
        self.root = root
        self.meetings = json.loads((root/'public/master_meetings_database_linked.json').read_text())
        self.records = []
        self.agendas=[]
        for p in sorted((root/'pipeline/docs').glob('**/*agenda.html')):
            parser=AgendaParser();parser.feed(p.read_text(errors='replace'))
            self.agendas.append(dict(title=p.stem.replace('_',' '),path=str(p.relative_to(root)),items=parser.items))
            text='\n'.join(i['title'] for i in parser.items)
            self.records.append(dict(id='agenda_'+p.parent.name,title=p.stem.replace('_',' '),date=p.name[:10],kind='Archived agenda',text=text,path=str(p.relative_to(root)),terms=terms(text)))
        for m in self.meetings:
            text = '\n'.join(t.get('text','') for t in m.get('turns',[]))
            self.records.append(dict(id=m['id'], title=m['title'], date=m.get('date'), kind='Meeting transcript', text=text, path='public/master_meetings_database_linked.json', terms=terms(text)))
        for p in sorted(root.rglob('*.md')):
            rel=p.relative_to(root)
            if any(x.startswith('.') or x in {'node_modules','agent','legacy','civic_atlas'} for x in rel.parts) or p.stat().st_size > 1500000: continue
            text=p.read_text(errors='replace')
            self.records.append(dict(id='doc_'+hashlib.sha256(str(rel).encode()).hexdigest()[:12],title=next((l.lstrip('# ').strip() for l in text.splitlines() if l.startswith('# ')),p.stem),date='',kind='Repository document',text=text,path=str(rel),terms=terms(text)))
        self.byid={r['id']:r for r in self.records}
    def search(self,q,limit=24,exclude=None):
        words=terms(q)
        if not words:return []
        hits=[]
        for r in self.records:
            if r['id']==exclude:continue
            common=words & r['terms']
            if not common:continue
            score=len(common)/len(words) + (2 if q.lower() in r['text'].lower() else 0)
            pos=next((r['text'].lower().find(w) for w in sorted(common,key=len,reverse=True)),0)
            hits.append((score,dict(id=r['id'],title=r['title'],date=r['date'],kind=r['kind'],path=r['path'],excerpt=r['text'][max(0,pos-120):pos+450],matched=sorted(common),relation='Text match · review required')))
        return [v for _,v in sorted(hits,key=lambda v:-v[0])[:limit]]

class Handler(BaseHTTPRequestHandler):
    corpus=None
    def json(self,data,status=200):
        blob=json.dumps(data).encode();self.send_response(status);self.send_header('Content-Type','application/json');self.send_header('Content-Length',str(len(blob)));self.end_headers();self.wfile.write(blob)
    def do_GET(self):
        u=urlparse(self.path);q=parse_qs(u.query)
        if u.path=='/api/catalog':
            return self.json(dict(meetings=[{k:m.get(k) for k in ['id','title','date','category','agendas','minutes','supporting_documents']} for m in self.corpus.meetings],count=len(self.corpus.records),agendas=self.corpus.agendas,topics=TOPICS,videos=[p.name for p in (ROOT/'video').glob('*.mp4')]))
        if u.path=='/api/search':return self.json(self.corpus.search(q.get('q',[''])[0],exclude=q.get('exclude',[None])[0]))
        if u.path=='/api/record':
            r=self.corpus.byid.get(q.get('id',[''])[0]);return self.json({k:v for k,v in r.items() if k!='terms'} if r else {'error':'Record not found'},200 if r else 404)
        if u.path.startswith('/media/'):
            name=unquote(u.path[len('/media/'):]);p=ROOT/'video'/name
            if Path(name).name!=name or p.suffix!='.mp4':return self.send_error(404)
        else:
            name=u.path.lstrip('/') or 'index.html'
            static_files={'index.html','app.js','lens.js','style.css',
                          'osint.html','osint-atlas.html','osint-original.html',
                          'osint/app.js','osint/style.css'}
            if name not in static_files:return self.send_error(404)
            p=WEB/name
        if not p.is_file():return self.send_error(404)
        size=p.stat().st_size;start=0;end=size-1
        match=re.fullmatch(r'bytes=(\d+)-(\d*)',self.headers.get('Range',''))
        if match:
            start=int(match[1]);end=min(int(match[2]) if match[2] else end,end)
            if start>end:self.send_response(416);self.send_header('Content-Range',f'bytes */{size}');self.end_headers();return
        self.send_response(206 if match else 200);self.send_header('Content-Type',mimetypes.guess_type(p.name)[0] or 'application/octet-stream');self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(end-start+1))
        if match:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
        self.end_headers()
        try:
            with p.open('rb') as f:
                f.seek(start);left=end-start+1
                while left:
                    chunk=f.read(min(left,65536))
                    if not chunk:break
                    self.wfile.write(chunk);left-=len(chunk)
        except (BrokenPipeError,ConnectionResetError):pass

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--port',type=int,default=8080);args=ap.parse_args()
    Handler.corpus=Corpus();print(f'Civic Atlas: {len(Handler.corpus.records)} indexed records',flush=True)
    ThreadingHTTPServer(('0.0.0.0',args.port),Handler).serve_forever()
if __name__=='__main__':main()
