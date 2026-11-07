import json
import subprocess
from pathlib import Path
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

def duration(path):
    return float(subprocess.check_output(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=nw=1:nk=1', str(path)], text=True))

p = Path('provenance/ledger.py')
text = p.read_text()
old = '"showcase": {"src": CLIP_SHOWCASE, "start": schedule["timelapse"],\n                             "end": round(schedule["timelapse"] + _timelapse_total(), 2)}'
assert text.count(old) == 2, 'Generator changed: inspect before patching'
text = text.replace(old, '"showcase": {"src": CLIP_SHOWCASE, "start": round(_timelapse_total() + start, 2),\n                             "end": round(_timelapse_total() + start + dur, 2)}', 1)
text = text.replace(old, '"showcase": {"src": CLIP_SHOWCASE, "start": 0.0,\n                             "end": round(_timelapse_total(), 2)}', 1)
old = '"src": CLIP_SHOWCASE,\n                "start": schedule["timelapse"],\n                "end": round(schedule["timelapse"] + _timelapse_total(), 2)'
assert text.count(old) == 1
text = text.replace(old, '"src": CLIP_SHOWCASE,\n                "start": 0.0,\n                "end": round(_timelapse_total(), 2)')
text = text.replace('"timelapse": round(total + 0.4, 2)', '"timelapse": round(total, 2)')
compile(text, str(p), 'exec')
p.write_text(text)
ledger = json.loads(Path('data/out/provenance-ledger.json').read_text())
prefix = duration(ledger['film']['timelapse'])
showcase_length = duration(ledger['film']['showcase'])
ledger['film']['schedule']['timelapse'] = ledger['film']['schedule']['total']
for row in ledger['data']:
    cue = row['cue']
    if cue.get('chapter') == 'overview':
        cue['start'], cue['end'] = 0.0, round(prefix, 2)
        cue['showcase'] = {'src': ledger['film']['showcase'], 'start': 0.0, 'end': round(prefix, 2)}
    else:
        start, end = cue['master']['start'], cue['master']['end']
        cue['showcase'] = {'src': ledger['film']['showcase'], 'start': round(prefix + start, 2), 'end': round(prefix + end, 2)}
        assert 0 <= cue['showcase']['start'] < cue['showcase']['end'] <= showcase_length + 0.5
        length = duration(cue['src'])
        for key in ('beat_start', 'beat_end'):
            if key in cue:
                assert 0 <= cue[key] - cue['start'] <= length + 0.2, row['id'] + ': beat outside clip'
from provenance.ledger import write
write(Path('.'), ledger)
print('Corrected chapter offsets and overview windows; regenerated ledger and manifest without changing collection counts.')
