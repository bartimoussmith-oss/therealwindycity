import { useMemo, useRef, useState } from 'react';
import { getTuning, stringNames } from '../dsp/tuning';
import { fmtTime, makeLabeler, songPrefs, uniqueChords, type DisplayPrefs } from '../app/labels';
import { navigate } from '../app/router';
import { notify, removeSong, reindexAll } from '../app/session';
import { tuneTo } from '../app/tunerTarget';
import { exportLibrary, importLibrary, library, updateSong } from '../lib/library';
import { getLyrics, searchLyrics, type LrclibTrack } from '../lib/lrclib';
import type { SongRecord } from '../lib/songModel';
import { useStore } from '../lib/store';
import { isLrc, parseLrc, plainToLines } from '../music/lrc';
import { buildSheet, sheetToText } from '../music/sheet';
import { Diagram, DisplayControls, Icon, SheetLineView, TuningCard, prettyChord } from './widgets';

function download(name: string, text: string, type = 'application/json') {
  const url = URL.createObjectURL(new Blob([text], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

function safeName(s: string): string {
  return s.replace(/[^\w\- ]+/g, '').trim().replace(/\s+/g, '-').slice(0, 60) || 'song';
}

export function LibraryView() {
  const { songs, loaded, error } = useStore(library, (x) => x);
  const [q, setQ] = useState('');
  const fileRef = useRef<HTMLInputElement>(null);
  const shown = songs.filter((s) => `${s.title} ${s.artist}`.toLowerCase().includes(q.toLowerCase()));
  return (
    <div className="view library">
      <div className="lib-head">
        <h1>Songs</h1>
        <div className="lib-actions">
          <button className="btn" onClick={() => fileRef.current?.click()}><Icon name="upload" /> Import</button>
          <input ref={fileRef} type="file" accept=".json,application/json" hidden onChange={async (e) => {
            const f = e.target.files?.[0];
            e.target.value = '';
            if (!f) return;
            try {
              const added = await importLibrary(await f.text());
              reindexAll();
              notify('info', `Imported ${added.length} song${added.length === 1 ? '' : 's'}.`);
            } catch (err) { notify('error', err instanceof Error ? err.message : String(err)); }
          }} />
          <button className="btn" disabled={!songs.length} onClick={() => download(`tunealong-library-${new Date().toISOString().slice(0, 10)}.json`, exportLibrary())}><Icon name="download" /> Export all</button>
        </div>
      </div>
      {error && <p className="error">{error}</p>}
      {songs.length > 3 && (
        <label className="search"><Icon name="search" /><input placeholder="Search songs" value={q} onChange={(e) => setQ(e.target.value)} /></label>
      )}
      {loaded && !songs.length && (
        <div className="card empty">
          <p>No songs yet. Go to <a href="#/listen">Listen</a> and play something — or try the demo song.</p>
        </div>
      )}
      <ul className="song-list">
        {shown.map((s) => (
          <li key={s.id}>
            <button className="song-row card" onClick={() => navigate(`/song/${s.id}`)}>
              <div className="song-main">
                <b>{s.title}</b>
                <span className="muted">{s.artist || (s.source === 'demo' ? 'Demo' : 'Unknown artist')}</span>
              </div>
              <div className="song-badges">
                {s.key && <span className="badge">{prettyChord(s.key.label.replace(' major', '').replace(' minor', 'm'))}</span>}
                <span className="badge">{getTuning(s.prefs.tuningId ?? s.tuning.candidates[0].id).short}</span>
                {s.lyrics && <span className="badge">words</span>}
                <span className="muted small">{fmtTime(s.duration)} · heard {s.listens}×</span>
              </div>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

export function SongView({ id }: { id: string }) {
  const song = useStore(library, (x) => x.songs.find((s) => s.id === id));
  if (!song) {
    return (
      <div className="view"><p>Song not found. <a href="#/songs">Back to songs</a></p></div>
    );
  }
  return <SongDetail song={song} />;
}

function SongDetail({ song }: { song: SongRecord }) {
  const prefs = songPrefs(song);
  const labeler = useMemo(() => makeLabeler(song.key, prefs), [song.key, prefs.mode, prefs.capo, prefs.tuningId]); // eslint-disable-line react-hooks/exhaustive-deps
  const setPrefs = (p: DisplayPrefs) => void updateSong(song.id, { prefs: { ...song.prefs, display: p.mode, capo: p.capo, tuningId: p.tuningId } });
  const synced = !!song.lyrics?.synced;
  const sheet = useMemo(
    () => buildSheet(song.chords, synced ? song.lyrics!.lines : [], { label: (c) => labeler.label(c), lyricsOffset: song.lyricsOffset }),
    [song.chords, song.lyrics, song.lyricsOffset, synced, labeler],
  );
  const chords = uniqueChords(song.chords);
  const tuning = getTuning(prefs.tuningId);
  const capoText = prefs.capo ? ` · Capo ${prefs.capo}` : '';
  return (
    <div className="view song">
      <div className="no-print song-top">
        <button className="btn ghost" onClick={() => navigate('/songs')}><Icon name="back" /> Songs</button>
        <div className="song-actions">
          <button className="btn primary" onClick={() => window.print()}><Icon name="print" /> Print / PDF</button>
          <button className="btn" onClick={() => { void navigator.clipboard?.writeText(`${song.title}${song.artist ? ' — ' + song.artist : ''}\n\n${sheetToText(sheet)}`).then(() => notify('info', 'Chord sheet copied as text.')); }}>Copy text</button>
          <button className="btn" onClick={() => download(`${safeName(song.title)}.tunealong.json`, exportLibrary([song.id]))}><Icon name="download" /> Export</button>
          <button className="btn danger" onClick={async () => { if (confirm(`Forget “${song.title}”?`)) { await removeSong(song.id); navigate('/songs'); } }}><Icon name="trash" /> Delete</button>
        </div>
      </div>

      <section className="card no-print song-meta">
        <label>Title<input defaultValue={song.title} onBlur={(e) => e.target.value.trim() && e.target.value !== song.title && void updateSong(song.id, { title: e.target.value.trim() })} /></label>
        <label>Artist<input defaultValue={song.artist} placeholder="Who plays it?" onBlur={(e) => e.target.value !== song.artist && void updateSong(song.id, { artist: e.target.value.trim() })} /></label>
        <p className="muted small">Heard {song.listens}× · {fmtTime(song.duration)} of music remembered · first learned {new Date(song.createdAt).toLocaleDateString()}</p>
      </section>

      <div className="song-grid no-print">
        <TuningCard report={song.tuning} keyResult={song.key} bpm={song.bpm} onTune={() => { tuneTo(prefs.tuningId, song.tuning.refHz); navigate('/tuner'); }} />
        <section className="card">
          <DisplayControls prefs={prefs} onChange={setPrefs} report={song.tuning} />
        </section>
      </div>

      <LyricsTools song={song} />

      <article className="print-area card">
        <header className="sheet-head">
          <h1>{song.title}</h1>
          {song.artist && <p className="sheet-artist">{song.artist}</p>}
          <p className="sheet-facts">
            {song.key && <>Key {prettyChord(song.key.label)} · </>}
            Tuning {tuning.short} ({prettyChord(stringNames(tuning))}) · A = {song.tuning.refHz.toFixed(1)} Hz
            {song.bpm ? <> · {Math.round(song.bpm)} BPM</> : null}{capoText}
            {prefs.mode === 'shape' && labeler.shift !== 0 ? ' · chord names are shapes' : ''}
          </p>
        </header>
        {labeler.diagramsApply && chords.length > 0 && (
          <div className="diagram-row">
            {chords.map((c) => (
              <figure key={`${c.root}-${c.type}`}>
                <Diagram chord={c} labeler={labeler} size={64} />
                <figcaption>{prettyChord(labeler.label(c))}</figcaption>
              </figure>
            ))}
          </div>
        )}
        <div className="sheet">
          {sheet.map((l, i) => <SheetLineView key={i} line={l} />)}
          {!sheet.length && <p className="muted">No chords were detected.</p>}
        </div>
        {song.lyrics && !synced && (
          <div className="plain-lyrics">
            <h3>Words</h3>
            <pre className="words">{song.lyrics.lines.map((l) => l.text).join('\n')}</pre>
          </div>
        )}
        <footer className="sheet-foot">Written down by TuneAlong from listening — check it by ear. {song.lyrics?.source === 'lrclib' ? 'Lyrics: LRCLIB (community).' : ''}</footer>
      </article>
    </div>
  );
}

function LyricsTools({ song }: { song: SongRecord }) {
  const [open, setOpen] = useState(!song.lyrics);
  const [title, setTitle] = useState(song.title.startsWith('Untitled song') ? '' : song.title);
  const [artist, setArtist] = useState(song.artist);
  const [results, setResults] = useState<LrclibTrack[] | null>(null);
  const [busy, setBusy] = useState(false);
  const [paste, setPaste] = useState('');
  const [err, setErr] = useState<string | null>(null);

  const useTrack = async (t: LrclibTrack) => {
    const lines = t.syncedLyrics ? parseLrc(t.syncedLyrics) : plainToLines(t.plainLyrics ?? '', 0, song.duration);
    await updateSong(song.id, {
      lyrics: { lines, synced: !!t.syncedLyrics, source: 'lrclib', lrclibId: t.id },
      title: song.title.startsWith('Untitled song') ? t.trackName : song.title,
      artist: song.artist || t.artistName,
      lyricsOffset: 0,
    });
    setResults(null);
    setOpen(false);
    notify('info', t.syncedLyrics ? 'Timed lyrics added. Use the timing buttons if they run early or late.' : 'Lyrics added (no timing available, so they print below the chords).');
  };

  const search = async () => {
    if (!title.trim()) { setErr('Type the song title first.'); return; }
    setBusy(true); setErr(null);
    try {
      const exact = artist.trim() ? await getLyrics(title, artist, song.duration) : null;
      const list = await searchLyrics(title, artist);
      setResults(exact ? [exact, ...list.filter((x) => x.id !== exact.id)] : list);
    } catch (e) {
      setErr(`Lyrics search failed: ${e instanceof Error ? e.message : String(e)}`);
    } finally { setBusy(false); }
  };

  const savePaste = async () => {
    const text = paste.trim();
    if (!text) return;
    const synced = isLrc(text);
    const lines = synced ? parseLrc(text) : plainToLines(text, 0, song.duration);
    await updateSong(song.id, { lyrics: { lines, synced, source: 'manual' }, lyricsOffset: 0 });
    setPaste('');
    setOpen(false);
  };

  const nudge = (d: number) => void updateSong(song.id, { lyricsOffset: Math.round((song.lyricsOffset + d) * 100) / 100 });

  return (
    <section className="card no-print lyrics-tools">
      <div className="row between">
        <h2>Words</h2>
        {song.lyrics && <button className="linklike" onClick={() => setOpen(!open)}>{open ? 'Close' : 'Change words'}</button>}
      </div>
      {song.lyrics && (
        <div className="row wrap">
          <span className="muted small">{song.lyrics.lines.length} lines · {song.lyrics.synced ? 'timed' : 'not timed'} · source: {song.lyrics.source}</span>
          {song.lyrics.synced && (
            <div className="stepper" aria-label="Lyrics timing">
              <span title="Move the words if they show up too early or too late">Words timing</span>
              <button onClick={() => nudge(1)} title="Show words 1 s later">later 1 s</button>
              <button onClick={() => nudge(0.25)} title="Show words ¼ s later">¼</button>
              <b title="Shift applied to the lyric timestamps">{song.lyricsOffset > 0 ? '+' : ''}{song.lyricsOffset.toFixed(2)} s</b>
              <button onClick={() => nudge(-0.25)} title="Show words ¼ s earlier">¼</button>
              <button onClick={() => nudge(-1)} title="Show words 1 s earlier">earlier 1 s</button>
            </div>
          )}
          <button className="btn small ghost" onClick={() => void updateSong(song.id, { lyrics: null })}>Remove words</button>
        </div>
      )}
      {open && (
        <div className="lyrics-forms">
          <div className="form-row">
            <input placeholder="Song title" value={title} onChange={(e) => setTitle(e.target.value)} />
            <input placeholder="Artist" value={artist} onChange={(e) => setArtist(e.target.value)} />
            <button className="btn primary" onClick={() => void search()} disabled={busy}><Icon name="search" /> {busy ? 'Searching…' : 'Find lyrics'}</button>
          </div>
          <p className="muted small">Searches LRCLIB, a free community lyrics library. Timed lyrics line up with the chords automatically.</p>
          {err && <p className="error">{err}</p>}
          {results && (
            <ul className="lrc-results">
              {results.length === 0 && <li className="muted">Nothing found. Try a shorter title or paste the words below.</li>}
              {results.map((r) => (
                <li key={r.id}>
                  <div><b>{r.trackName}</b> — {r.artistName} <span className="muted small">{r.albumName ?? ''} {r.duration ? `· ${fmtTime(r.duration)}` : ''} · {r.syncedLyrics ? 'timed' : r.instrumental ? 'instrumental' : 'not timed'}</span></div>
                  <button className="btn small" disabled={!r.syncedLyrics && !r.plainLyrics} onClick={() => void useTrack(r)}>Use</button>
                </li>
              ))}
            </ul>
          )}
          <details>
            <summary>Paste the words yourself</summary>
            <textarea rows={6} value={paste} onChange={(e) => setPaste(e.target.value)} placeholder={'Paste lyrics here. Timed LRC ([00:12.50] like this) lines up with the chords;\nplain text prints underneath the chord chart.'} />
            <button className="btn" onClick={() => void savePaste()} disabled={!paste.trim()}>Save words</button>
          </details>
          {song.transcript.length > 0 && (
            <button className="btn ghost" onClick={() => void updateSong(song.id, { lyrics: { lines: song.transcript, synced: true, source: 'transcript' }, lyricsOffset: 0 })}>
              Use the {song.transcript.length} lines TuneAlong heard
            </button>
          )}
        </div>
      )}
    </section>
  );
}
