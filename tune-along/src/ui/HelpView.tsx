export function HelpView() {
  return (
    <div className="view help">
      <h1>Help</h1>
      <section className="card">
        <h2>Getting good results</h2>
        <ul>
          <li><b>Phone near the speaker.</b> Closer is better than louder. Turn off any “voice isolation” mode.</li>
          <li><b>On a computer,</b> choose <i>Tab audio</i> and share the tab that is playing (YouTube, Spotify Web, Bandcamp…). That gives TuneAlong a perfect copy of the sound.</li>
          <li><b>Let the song play to the end</b> the first time (or press Stop). Each later play fills in anything it missed — even if you came in halfway the first time.</li>
          <li><b>Playlists:</b> TuneAlong treats 2–3 seconds of quiet as the end of a song. Songs that crossfade into each other may be saved as one.</li>
        </ul>
      </section>
      <section className="card">
        <h2>What the tuning card means</h2>
        <p><b>Reference pitch (A = … Hz)</b> is measured from the recording. Many older records run a little fast or slow; tune your A string to this and you’ll be in tune with the record.</p>
        <p><b>Guitar tuning</b> (Standard, Eb Standard, Drop D…) is an informed guess. TuneAlong listens for power chords below a standard guitar’s low E and checks which tuning makes the chords easy shapes. It tells you how sure it is. When the record is in an awkward key it may suggest a <b>capo</b> instead.</p>
        <p><b>Sounding names vs. shapes:</b> “Sounding names” are the real chords on the record. “Shapes I play” are the chord shapes for your tuning and capo — e.g. a song in Eb played in Eb Standard shows familiar E-shapes.</p>
      </section>
      <section className="card">
        <h2>Over other apps (the overlay)</h2>
        <ul>
          <li><b>Desktop Chrome / Edge / Firefox:</b> press <i>Pop out</i> while listening — a small always-on-top window shows the chords over anything.</li>
          <li><b>Android (Chrome):</b> <i>Pop out</i> opens a picture-in-picture mini player where supported. Keep the phone near the speaker; a music app on the same phone can’t be heard by a web app directly.</li>
          <li><b>iPhone / iPad:</b> Apple doesn’t let apps draw over other apps or listen to other apps’ audio. Play music from another device (or a speaker) and keep TuneAlong on screen, or use split view on iPad.</li>
        </ul>
      </section>
      <section className="card">
        <h2>Privacy</h2>
        <p>All listening and analysis happen on this device. Audio is never uploaded or stored — only the analysis (chords, key, tuning and a compact “sound print” of hashes) is saved in this browser. Two optional features talk to the internet: <i>Find lyrics</i> (asks LRCLIB for the title you type) and <i>write down the words</i> (uses your browser’s speech recogniser, which may use the browser maker’s servers unless it supports on-device recognition).</p>
      </section>
      <section className="card">
        <h2>Honest limits</h2>
        <ul>
          <li>Chord detection is very good on clear guitar/piano parts and weaker on dense mixes, heavy distortion or jazz voicings. Treat the sheet as a strong first draft and trust your ears.</li>
          <li>“Write down the words” is experimental: speech recognisers are built for talking, not singing over a band.</li>
          <li>Recognition works for songs this device has heard (or that you imported). It doesn’t know songs it has never heard.</li>
        </ul>
      </section>
    </div>
  );
}
