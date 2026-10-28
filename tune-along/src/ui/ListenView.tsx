import { useMemo, useRef, useState } from 'react';
import { CHROMA_HOP_SEC } from '../dsp/chroma';
import { chordAt, stateToChord, type Chord, type ChordSegment } from '../dsp/chords';
import { DEMO_SONGS } from '../audio/demoSongs';
import { defaultPrefs, fmtTime, makeLabeler, songPrefs, type DisplayPrefs } from '../app/labels';
import { live, playDemo, sessionTimeNow, setTranscribe, songTimeNow, startListening, stopListening } from '../app/session';
import { tuneTo } from '../app/tunerTarget';
import { navigate } from '../app/router';
import { openOverlay, overlaySupport } from './Overlay';
import { library, updateSong } from '../lib/library';
import { speechSupported } from '../lib/speech';
import { useStore } from '../lib/store';
import { ChordLane, ChordName, ChromaBars, Diagram, DisplayControls, Icon, LyricsLive, TuningCard, useAnimationClock, useSheet } from './widgets';

export function ListenView() {
  const status = useStore(live, (s) => s.status);
  return status === 'idle' || status === 'starting' ? <StartPanel /> : <LivePanel />;
}

function StartPanel() {
  const s = useStore(live, (x) => x);
  const songs = useStore(library, (x) => x.songs);
  const fileRef = useRef<HTMLInputElement>(null);
  const starting = s.status === 'starting';
  const tabOk = typeof navigator !== 'undefined' && !!navigator.mediaDevices && 'getDisplayMedia' in navigator.mediaDevices && !/Android|iPhone|iPad/i.test(navigator.userAgent);
  return (
    <div className="view start">
      <section className="hero card">
        <p className="eyebrow">Tune Along · Play Along</p>
        <h1>Hear it once.<br />Play along every time after.</h1>
        <p className="lead">Put TuneAlong next to the music. The first time it hears a song it writes down the <b>chords</b>, <b>key</b>, <b>tempo</b> and <b>tuning</b>. The next time that song plays, it recognises it within seconds and shows what’s coming — with the words.</p>
        <div className="big-actions">
          <button className="listen-btn" onClick={() => startListening('mic')} disabled={starting} aria-label="Start listening with the microphone">
            <span className="pulse" />
            <Icon name="mic" size={40} />
            <span>{starting ? 'Starting…' : 'Listen'}</span>
          </button>
          <div className="source-list">
            <button className="btn" onClick={() => startListening('tab')} disabled={starting || !tabOk} title={tabOk ? 'Capture a browser tab (YouTube, Spotify Web…)' : 'Needs desktop Chrome or Edge'}>
              <Icon name="tab" /> Tab audio {tabOk ? '' : <small>(desktop Chrome/Edge)</small>}
            </button>
            <button className="btn" onClick={() => fileRef.current?.click()} disabled={starting}><Icon name="file" /> Audio file…</button>
            <input ref={fileRef} type="file" accept="audio/*" hidden onChange={(e) => { const f = e.target.files?.[0]; if (f) void startListening('file', { file: f }); e.target.value = ''; }} />
            <label className={`toggle ${speechSupported() ? '' : 'disabled'}`} title={speechSupported() ? '' : 'This browser has no speech recogniser'}>
              <input type="checkbox" checked={s.transcribe} disabled={!speechSupported()} onChange={(e) => setTranscribe(e.target.checked)} />
              <span>Also write down the words <em>(experimental)</em></span>
            </label>
          </div>
        </div>
        {s.error && <p className="error" role="alert">{s.error}</p>}
        <p className="muted small">{songs.length ? `${songs.length} song${songs.length === 1 ? '' : 's'} remembered on this device.` : 'No songs remembered yet.'} Everything is analysed on this device — no audio is uploaded.</p>
      </section>

      <section className="card demo-card">
        <h2><Icon name="play" /> No music handy? Try the demo</h2>
        <ol className="steps">
          <li><b>Play a demo song.</b> TuneAlong hears it for the first time and writes down the chords, key and tuning while it plays.</li>
          <li><b>Play it again.</b> It recognises the song in a few seconds and shows the chords <i>before</i> they happen, the words, and the tuning.</li>
        </ol>
        <div className="demo-buttons">
          {DEMO_SONGS.map((d) => (
            <button key={d.id} className="btn primary" onClick={() => playDemo(d.id)} disabled={starting}>
              <Icon name="play" /> {d.title} <small>{d.refCents ? '½ step down, A≈436' : 'standard, A440'}</small>
            </button>
          ))}
        </div>
        <p className="muted small">The demo songs are original, synthesised in your browser and fed straight to the analyser, so they also work without a microphone.</p>
      </section>

      <section className="card how">
        <h2>How it works</h2>
        <div className="how-grid">
          <div><b>1 · Listen</b><p>Hold your phone near the speaker, or on a computer capture the browser tab that’s playing.</p></div>
          <div><b>2 · Learn</b><p>New song? TuneAlong works out chords, key, tempo and the guitar tuning, then remembers the song’s “sound print”.</p></div>
          <div><b>3 · Play along</b><p>Known song? It lines up to the exact spot and scrolls the chords and words with the music. Print a chord sheet any time.</p></div>
        </div>
      </section>
    </div>
  );
}

function historyToSegments(history: { t: number; state: number }[], now: number): ChordSegment[] {
  const out: ChordSegment[] = [];
  for (let i = 0; i < history.length; i++) {
    const c = stateToChord(history[i].state);
    const end = i + 1 < history.length ? history[i + 1].t : now;
    out.push({ start: history[i].t - CHROMA_HOP_SEC * 2, end: end - CHROMA_HOP_SEC * 2, root: c.root, type: c.type, confidence: 1 });
  }
  return out;
}

function LivePanel() {
  const s = useStore(live, (x) => x);
  const songs = useStore(library, (x) => x.songs);
  const song = s.match ? songs.find((x) => x.id === s.match!.songId) ?? null : null;
  const [localPrefs, setLocalPrefs] = useState<DisplayPrefs | null>(null);
  const clock = useAnimationClock(s.status === 'listening', 30);
  void clock;
  const songNow = songTimeNow(s);
  const sessNow = sessionTimeNow(s);

  const prefs: DisplayPrefs = song ? songPrefs(song) : localPrefs ?? defaultPrefs(s.tuning);
  const setPrefs = (p: DisplayPrefs) => {
    if (song) void updateSong(song.id, { prefs: { ...song.prefs, display: p.mode, capo: p.capo, tuningId: p.tuningId } });
    else setLocalPrefs(p);
  };
  const keyResult = song?.key ?? s.key;
  const report = song?.tuning ?? s.tuning;
  const labeler = useMemo(() => makeLabeler(keyResult, prefs), [keyResult, prefs.mode, prefs.capo, prefs.tuningId]); // eslint-disable-line react-hooks/exhaustive-deps
  const lyricLines = song?.lyrics?.lines ?? [];
  const sheet = useSheet(song?.chords ?? [], lyricLines, labeler, song?.lyricsOffset ?? 0);

  let current: Chord | null = null;
  let next: ChordSegment | null = null;
  let countdown = 0;
  let laneChords: ChordSegment[] = [];
  let laneNow = sessNow;
  if (song && songNow !== null) {
    const idx = chordAt(song.chords, songNow);
    current = idx >= 0 ? song.chords[idx] : null;
    for (let k = Math.max(0, idx + 1); k < song.chords.length; k++) {
      if (song.chords[k].type !== 'N' && song.chords[k].start > songNow) { next = song.chords[k]; break; }
    }
    countdown = next ? next.start - songNow : 0;
    laneChords = song.chords;
    laneNow = songNow;
  } else if (s.frame) {
    current = s.music ? stateToChord(s.frame.state) : null;
    laneChords = historyToSegments(s.history, s.frame.t);
    laneNow = s.frame.t;
  }

  const demoSpec = s.input === 'demo' && s.demo ? DEMO_SONGS.find((d) => d.id === s.demo!.id) : null;
  const pip = overlaySupport();
  const level = Math.min(1, (s.frame?.rms ?? 0) * 6);

  return (
    <div className="view live">
      <div className="status-bar card">
        <div className="status-left">
          <span className={`rec-dot ${s.music ? 'on' : ''}`} style={{ ['--lvl' as string]: level }} />
          <div>
            <div className="status-title">
              {s.status === 'stopping' ? 'Finishing…' : song ? <>Playing along: <b>{song.title}</b></> : s.music ? 'Learning a new song…' : 'Listening — waiting for music'}
            </div>
            <div className="muted small">{s.inputLabel} · {fmtTime(sessNow)}{song && songNow !== null ? ` · song position ${fmtTime(songNow)} / ${fmtTime(song.duration)}` : ''}{s.match && !song ? ' · recognised' : ''}</div>
          </div>
        </div>
        <div className="status-actions">
          {pip !== 'none' && <button className="btn" onClick={() => void openOverlay()} title={pip === 'document' ? 'Float a mini window over other apps' : 'Float a mini player (picture-in-picture)'}><Icon name="pip" /> Pop out</button>}
          <button className="btn danger" onClick={() => void stopListening()} disabled={s.status === 'stopping'}><Icon name="stop" /> Stop</button>
        </div>
      </div>

      {demoSpec && <DemoGuide />}

      {!song && s.music && (
        <p className="banner learn">First listen: TuneAlong is writing this song down. Keep it playing to the end (or press Stop) and it will be remembered.</p>
      )}
      {song && <p className="banner known"><Icon name="check" /> Recognised from memory — chords and words are scrolling with the music.</p>}

      <div className="live-grid">
        <section className="card now-next">
          <div className="now">
            <span className="eyebrow">{song ? 'Now' : 'Hearing'}</span>
            <ChordName chord={current} labeler={labeler} />
            <Diagram chord={current} labeler={labeler} size={110} />
          </div>
          <div className="next">
            <span className="eyebrow">Next</span>
            {song ? (
              next ? (
                <>
                  <ChordName chord={next} labeler={labeler} size="lg" />
                  <div className="countdown" aria-label={`in ${countdown.toFixed(1)} seconds`}>
                    <div className="countdown-fill" style={{ width: `${Math.max(0, Math.min(100, 100 - (countdown / 4) * 100))}%` }} />
                    <span>in {countdown.toFixed(1)} s</span>
                  </div>
                  <Diagram chord={next} labeler={labeler} size={78} />
                </>
              ) : <div className="muted">End of song</div>
            ) : (
              <p className="muted small">Shown when TuneAlong knows the song. First listens show what is sounding now.</p>
            )}
          </div>
        </section>

        <TuningCard report={report} keyResult={keyResult} bpm={song?.bpm ?? s.bpm} learning={!song} onTune={() => { if (report) tuneTo(prefs.tuningId || report.candidates[0].id, report.refHz); navigate('/tuner'); }} />
      </div>

      <section className="card">
        <ChordLane chords={laneChords} now={laneNow} labeler={labeler} before={song ? 3 : 12} after={song ? 12 : 0.5} />
        {song && sheet.length > 0 && songNow !== null && <LyricsLive sheet={sheet} now={songNow} />}
        {song && !song.lyrics && <p className="muted small">No words saved for this song yet — open it in <a href={`#/song/${song.id}`}>Songs</a> to find or paste lyrics.</p>}
        {!song && s.transcribe && (
          <div className="transcript">
            <span className="eyebrow">Words heard {s.transcriberLocal ? '(on-device)' : ''}</span>
            <p>{s.transcript.slice(-3).map((l) => l.text).join(' / ')} <span className="muted">{s.interim}</span></p>
          </div>
        )}
      </section>

      <section className="card controls-card">
        <DisplayControls prefs={prefs} onChange={setPrefs} report={report} />
        {!song && <ChromaBars chroma={s.frame?.chroma ?? null} keyResult={keyResult} lowest={s.frame?.lowest ?? null} />}
      </section>
    </div>
  );
}

function DemoGuide() {
  const s = useStore(live, (x) => x);
  const spec = DEMO_SONGS.find((d) => d.id === s.demo!.id)!;
  const learned = !!s.demo?.learnedSongId;
  const matched = s.match && s.match.songId === s.demo?.learnedSongId;
  let text: string;
  if (matched) text = `Second play: recognised “${spec.title}” from memory. The tuning card was ready at the intro and the next chord shows before it happens.`;
  else if (learned && !s.music) text = 'Learned! Now play it again — this time TuneAlong will recognise it within a few seconds.';
  else if (learned) text = 'Playing again… listening for a match.';
  else if (s.music) text = `First play of “${spec.title}”: watch it write down chords, key, tempo and tuning. When the song ends (2–3 s of quiet) it is saved.`;
  else text = 'Starting the demo…';
  return (
    <div className="banner demo">
      <span>{text}</span>
      {learned && !s.music && <button className="btn primary" onClick={() => void playDemo(spec.id)}><Icon name="play" /> Play it again</button>}
    </div>
  );
}
