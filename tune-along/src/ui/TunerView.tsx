import { useEffect, useRef, useState } from 'react';
import { audioContext, isInsecureContext, needsSecureContextMessage } from '../audio/capture';
import { centsOff, freqToMidi, midiName, midiToFreq } from '../dsp/notes';
import { decimate, detectPitch } from '../dsp/pitch';
import { TUNINGS, getTuning } from '../dsp/tuning';
import { tunerTarget } from '../app/tunerTarget';
import { useStore } from '../lib/store';
import { Icon, prettyChord } from './widgets';

interface Reading { freq: number; clarity: number }

export function TunerView() {
  const target = useStore(tunerTarget, (x) => x);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reading, setReading] = useState<Reading | null>(null);
  const stopRef = useRef<() => void>(() => undefined);
  const history = useRef<number[]>([]);
  const tuning = getTuning(target.tuningId);
  const ref = target.refHz;
  const flats = (tuning.down ?? 0) > 0 && !tuning.drop;
  const sp = flats ? 'flat' : 'common';

  useEffect(() => () => stopRef.current(), []);

  const start = async () => {
    setError(null);
    if (isInsecureContext()) { setError(needsSecureContextMessage()); return; }
    try {
      const ctx = audioContext();
      if (ctx.state === 'suspended') await ctx.resume();
      const stream = await navigator.mediaDevices.getUserMedia({ audio: { echoCancellation: false, noiseSuppression: false, autoGainControl: false } });
      const src = ctx.createMediaStreamSource(stream);
      const an = ctx.createAnalyser();
      an.fftSize = 8192;
      src.connect(an);
      const buf = new Float32Array(an.fftSize);
      const factor = Math.max(1, Math.round(ctx.sampleRate / 11025));
      const sr = ctx.sampleRate / factor;
      const timer = window.setInterval(() => {
        an.getFloatTimeDomainData(buf);
        const p = detectPitch(decimate(buf.subarray(buf.length - 2048 * factor), factor), sr, { minFreq: 26, maxFreq: 1400, minRms: 0.003 });
        if (!p || p.clarity < 0.8) { if (history.current.length) history.current.shift(); if (!history.current.length) setReading(null); return; }
        history.current.push(p.freq);
        if (history.current.length > 5) history.current.shift();
        const sorted = [...history.current].sort((a, b) => a - b);
        setReading({ freq: sorted[Math.floor(sorted.length / 2)], clarity: p.clarity });
      }, 60);
      stopRef.current = () => {
        clearInterval(timer);
        src.disconnect();
        stream.getTracks().forEach((t) => t.stop());
        setRunning(false);
        setReading(null);
      };
      setRunning(true);
    } catch (err) {
      const name = (err as DOMException)?.name;
      setError(name === 'NotAllowedError' ? 'Microphone permission was denied.' : name === 'NotFoundError' ? 'No microphone was found.' : `Could not start the tuner: ${String(err)}`);
    }
  };

  const tone = (midi: number) => {
    const ctx = audioContext();
    void ctx.resume();
    const osc = ctx.createOscillator();
    const g = ctx.createGain();
    osc.type = 'triangle';
    osc.frequency.value = midiToFreq(midi, ref);
    g.gain.setValueAtTime(0, ctx.currentTime);
    g.gain.linearRampToValueAtTime(0.25, ctx.currentTime + 0.02);
    g.gain.exponentialRampToValueAtTime(0.001, ctx.currentTime + 2);
    osc.connect(g).connect(ctx.destination);
    osc.start();
    osc.stop(ctx.currentTime + 2.05);
  };

  // nearest string (by cents, octave-aware) and nearest chromatic note
  let nearest = -1, stringCents = 0, noteMidi = 0, noteCents = 0;
  if (reading) {
    const m = freqToMidi(reading.freq, ref);
    noteMidi = Math.round(m);
    noteCents = (m - noteMidi) * 100;
    let best = Infinity;
    tuning.strings.forEach((s, i) => {
      const c = centsOff(reading.freq, midiToFreq(s, ref));
      if (Math.abs(c) < Math.abs(best)) { best = c; nearest = i; }
    });
    stringCents = best;
    if (Math.abs(stringCents) > 350) nearest = -1;
  }
  const showCents = nearest >= 0 ? stringCents : noteCents;
  const inTune = reading && Math.abs(showCents) < 4;
  const angle = Math.max(-50, Math.min(50, showCents)) * 1.6;

  return (
    <div className="view tuner">
      <h1>Tuner</h1>
      {target.fromSong && <p className="banner known">Set from the song: {tuning.short}, A = {ref.toFixed(1)} Hz. Tune every string to the targets below and you will match the record.</p>}
      <section className="card tuner-controls">
        <label>Tuning
          <select value={target.tuningId} onChange={(e) => tunerTarget.set({ tuningId: e.target.value, fromSong: false })}>
            {TUNINGS.map((t) => <option key={t.id} value={t.id}>{t.name}</option>)}
          </select>
        </label>
        <label>Reference A4
          <span className="row">
            <input type="range" min={415} max={466} step={0.1} value={ref} onChange={(e) => tunerTarget.set({ refHz: Number(e.target.value), fromSong: false })} />
            <input type="number" min={400} max={480} step={0.1} value={ref} onChange={(e) => tunerTarget.set({ refHz: Number(e.target.value) || 440, fromSong: false })} />
            <span>Hz</span>
            {ref !== 440 && <button className="btn small ghost" onClick={() => tunerTarget.set({ refHz: 440, fromSong: false })}>440</button>}
          </span>
        </label>
      </section>

      <section className={`card tuner-face ${inTune ? 'in-tune' : ''}`}>
        <svg viewBox="0 0 200 110" className="needle-dial" aria-hidden="true">
          <path d="M20 100 A80 80 0 0 1 180 100" className="dial" />
          {[-50, -25, 0, 25, 50].map((c) => {
            const a = ((c * 1.6 - 90) * Math.PI) / 180;
            return <line key={c} x1={100 + 72 * Math.cos(a)} y1={100 + 72 * Math.sin(a)} x2={100 + 82 * Math.cos(a)} y2={100 + 82 * Math.sin(a)} className="tick" />;
          })}
          <line x1="100" y1="100" x2="100" y2="28" className="needle" style={{ transform: `rotate(${reading ? angle : 0}deg)`, transformOrigin: '100px 100px' }} />
          <circle cx="100" cy="100" r="5" className="hub" />
        </svg>
        <div className="tuner-note">{reading ? prettyChord(midiName(nearest >= 0 ? tuning.strings[nearest] : noteMidi, sp).replace(/-?\d+$/, '')) : '—'}</div>
        <div className="tuner-readout">
          {reading ? (
            <>
              <b>{showCents > 0 ? '+' : ''}{showCents.toFixed(0)}¢</b> · {reading.freq.toFixed(1)} Hz
              {nearest >= 0 && !inTune && <span> · tune {showCents < 0 ? 'up ↑' : 'down ↓'}</span>}
              {inTune && <span> · in tune ✓</span>}
            </>
          ) : running ? 'Play one string at a time…' : 'Press Start and play a string.'}
        </div>
        <div className="row center">
          {!running ? <button className="btn primary" onClick={() => void start()}><Icon name="mic" /> Start tuner</button> : <button className="btn" onClick={() => stopRef.current()}><Icon name="stop" /> Stop</button>}
        </div>
        {error && <p className="error">{error}</p>}
      </section>

      <section className="card strings">
        <p className="muted small">Targets for {tuning.name} at A = {ref.toFixed(1)} Hz. Tap a string to hear its note.</p>
        <div className="string-row">
          {tuning.strings.map((m, i) => (
            <button key={i} className={`string-btn ${i === nearest ? 'active' : ''}`} onClick={() => tone(m)}>
              <b>{prettyChord(midiName(m, sp).replace(/-?\d+$/, ''))}</b>
              <small>{midiToFreq(m, ref).toFixed(1)} Hz</small>
              <Icon name="sound" size={14} />
            </button>
          ))}
        </div>
      </section>
    </div>
  );
}
