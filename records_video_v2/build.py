import argparse
import html
import json
import os
from pathlib import Path
import subprocess
import tempfile
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
STEPS = [
    ('How the records are collected', 'Find the source. Save the record. Make it searchable. Keep the link.', 'A guide to the collection process'),
    ('1. Find the source', 'Open the public agency website. Find the meeting date, agenda, minutes, or recording.', 'Check the agency and meeting date'),
    ('2. Save the record', 'Download the available document or recording. Keep its original title and source address.', 'A link is not the same as a saved file'),
    ('3. Keep the evidence trail', 'Store the source URL, capture date, filename, and file fingerprint beside the record.', 'Preserve the original before processing'),
    ('4. Make it searchable', 'Extract document text. Use OCR for scans and transcription for speech. Keep the original available.', 'Machine text needs review'),
    ('5. Check before reporting', 'Check names, dates, numbers, and quotations against the original. Link published claims to their sources.', 'A count is not proof of complete coverage'),
]

def run(args):
    subprocess.run(args, check=True)

def font(size, bold=False):
    name = 'DejaVuSans-Bold.ttf' if bold else 'DejaVuSans.ttf'
    path = Path('/usr/share/fonts/truetype/dejavu') / name
    if not path.is_file():
        raise RuntimeError('Required font missing: ' + str(path))
    return ImageFont.truetype(str(path), size)

def wrapped(draw, text, face, width):
    lines, line = [], ''
    for word in text.split():
        trial = (line + ' ' + word).strip()
        if draw.textlength(trial, font=face) > width and line:
            lines.append(line)
            line = word
        else:
            line = trial
    return lines + ([line] if line else [])

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--format', choices=['wide', 'phone'], required=True)
    args = ap.parse_args()
    width, height = (1280, 720) if args.format == 'wide' else (720, 1280)
    out = ROOT / 'records-video-output' / args.format
    out.mkdir(parents=True, exist_ok=True)
    slides = list(STEPS)
    counts = {}
    for rel in ('pipeline/corpus_yt', 'ai-record-ocr', 'data/text'):
        base = ROOT / rel
        counts[rel] = sum(1 for p in base.rglob('*') if p.is_file() and not p.is_symlink()) if base.is_dir() else None
    count_text = '; '.join(rel + ': ' + (str(n) + ' files' if n is not None else 'folder absent') for rel, n in counts.items())
    slides.append(('Files in this checkout', count_text, 'Folder counts, not unique meetings or verified coverage'))
    pad = 55
    title_face, body_face, foot_face = font(44, True), font(30), font(21)
    chapters = []
    with tempfile.TemporaryDirectory() as temporary:
        tmp = Path(temporary)
        for i, (title, body, note) in enumerate(slides):
            image = Image.new('RGB', (width, height), '#101827')
            draw = ImageDraw.Draw(image)
            draw.rectangle((pad, 55, width-pad, 64), fill='#62d5b4')
            y = 105
            for line in wrapped(draw, title, title_face, width-2*pad):
                draw.text((pad, y), line, font=title_face, fill='white')
                y += 57
            y += 35
            for line in wrapped(draw, body, body_face, width-2*pad):
                draw.text((pad, y), line, font=body_face, fill='#cfdae8')
                y += 44
            assert y < height-160, 'Slide text overflow: ' + title
            y = height-145
            for line in wrapped(draw, note, foot_face, width-2*pad):
                draw.text((pad, y), line, font=foot_face, fill='#62d5b4')
                y += 29
            draw.text((pad, height-48), 'The Real Windy City | Process guide | ' + str(i+1) + '/' + str(len(slides)), font=font(17), fill='#9cacc2')
            still = tmp / (str(i) + '.png')
            image.save(still)
            clip = out / ('chapter-' + str(i+1).zfill(2) + '.mp4')
            run(['ffmpeg','-hide_banner','-loglevel','error','-y','-loop','1','-framerate','24','-i',str(still),'-t','6','-c:v','libx264','-preset','fast','-pix_fmt','yuv420p','-an','-movflags','+faststart',str(clip)])
            chapters.append({'title': title, 'start': i*6, 'end': (i+1)*6, 'file': clip.name})
        listing = tmp / 'concat.txt'
        listing.write_text(''.join("file '" + str((out / c['file']).resolve()) + "'\n" for c in chapters))
        film = out / 'how-records-are-collected.mp4'
        run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),'-c','copy','-movflags','+faststart',str(film)])
    for video in sorted(out.glob('*.mp4')):
        run(['ffmpeg','-v','error','-xerror','-i',str(video),'-f','null','-'])
    info = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_format','-show_streams','-of','json',str(film)], text=True))
    actual = float(info['format']['duration'])
    assert abs(actual-len(slides)*6) < 0.3, 'Unexpected duration'
    stream = next(s for s in info['streams'] if s['codec_type'] == 'video')
    assert (stream['width'], stream['height']) == (width, height)
    assert all(c['end'] <= actual+0.1 for c in chapters)
    report = {'title': 'How the records are collected', 'format': args.format, 'duration_seconds': actual, 'chapters': chapters, 'checkout_file_counts': counts, 'revision': os.environ.get('GITHUB_SHA', ''), 'scope': 'Process guide. Folder counts describe this checkout only. No live collection, full archive integration, or live-site publication is performed.', 'checks': {'full_decode': 'passed', 'duration': 'passed', 'dimensions': 'passed', 'chapter_bounds': 'passed'}}
    (out / 'report.json').write_text(json.dumps(report, indent=2))
    links = ''.join('<li><a href="' + c['file'] + '">' + html.escape(c['title']) + '</a></li>' for c in chapters)
    (out / 'index.html').write_text('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width"><title>How the records are collected</title><h1>How the records are collected</h1><video controls style="max-width:100%;max-height:80vh" src="how-records-are-collected.mp4"></video><ul>' + links + '</ul><p>Process guide. Not an official government publication.</p>')
    summary = os.environ.get('GITHUB_STEP_SUMMARY')
    if summary:
        with open(summary, 'a') as f:
            f.write('## Fresh video build: ' + args.format + '\nVideo and seven chapter clips generated. Playback, duration, dimensions, and chapter bounds checked. Download the run artifact and open index.html. Not deployed live.\n')

if __name__ == '__main__':
    main()
