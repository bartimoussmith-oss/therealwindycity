# EXECUTIVE MEMORANDUM — TuneAlong / Play-Along

**To:** Bartimous "Charlie" Smith (owner) · **Re:** Dennis's request, "WHAT DO YOU THINK? IS IT DONE YET?", and the proposed 51/49 split
**Date:** 2026-10-28 · **Status vocabulary:** implemented ≠ tested ≠ deployed ≠ verified live

---

## 0. Bottom line

1. **Is it done?** A working v0.1 exists in `tune-along/`.
   - Implemented and tested: 49 automated tests, 8/8 real-browser checks, and 10/10 recognitions on real recordings.
   - **Not deployed.**
   - **Not checked on real phones in real rooms.**
   - It does Dennis's core loop: hear once → write down chords, key, tempo and tuning → recognise on replay → show what's coming, with the words → print.
2. **Is it a good idea?** It is viable as a tool for players and bands. As a business it is crowded:
   - Chord ai, Moises and Chordify already do live chord detection and lyrics, at $40–$70 a year.
   - The real differentiators are narrow:
     - tuning and A-reference detection at the intro;
     - a learn-once / offline / private model;
     - printing chords **with** the words — Chordify's print deliberately omits lyrics, for licensing reasons.
3. **The hard limits are platform and legal, not code:**
   - iOS forbids overlays and listening to other apps.
   - Android needs a native app for both.
   - Displaying lyrics commercially requires paid licences.
4. **51/49:** an idea alone carries little legal weight. AI-written code carries thin copyright. The split should be set by a **written agreement** that covers contribution, control, vesting and IP. I am an AI assistant: I take no equity, and this is not legal advice.

---

## 1. Chronological / data audit

### 1.1 What was built (verified in this session)

| Item | Evidence | Confidence |
|---|---|---|
| Streaming analysis engine (chords, key, tempo, reference pitch, tuning inference, fingerprinting) | `src/dsp`, `src/engine`; 49 tests pass (`npm test`) | measured |
| Demo song, engine-level end to end | Chords: 100% (major/minor, per bar). Key: Eb major. 103.7 BPM vs 104 true. −15.8¢ vs −15¢ true. Eb Standard ranked first. | measured (synthetic) |
| Recognition under degradation | Synthetic: 3.6 s at 8 dB SNR with low-pass and echo. Real recordings (3 CC tracks): 10/10 recognised, exact position, median 3.6 s, 0 wrong-song, 0/3 false positives on songs not in the library. | measured, small sample |
| Real browser (headless Chrome 153) | Learn → recognise 3.0 s into the second play. Fake-mic path recognised after 9.3 s from pressing Listen. Pop-out window renders. 0 console errors. | measured |
| Chord accuracy on real commercial music | **Not measured** (no annotated set available here) | unknown |
| Tuning inference on real music | Calibrated, but ground truth is unavailable. For a Bb-major folk recording it says "Eb Standard 54%, best guess" and also offers "Standard + capo". | heuristic |
| Deployment / phones | none | not done |

### 1.2 Market facts

| Fact | Source |
|---|---|
| Chord ai detects chords live from the microphone, plus tonality and lyrics recognition/alignment. Pro costs $10.99/mo or $69.99/yr (US App Store). | play.google.com/store/apps/details?id=com.chordai · apps.apple.com/us/app/chord-ai-play-any-song/id1446177109 |
| Chordify: Premium $42/yr (PDF chord sheets); Premium Plus $54/yr, first year $27 (Toolkit, including "Generate Lyrics" and live chord detection). | chordify.net/premium · chordify.net/toolkit/live-chord-detection |
| Chordify's PDF and print **never include lyrics**: "only displayed online for licensing reasons". | support.chordify.net articles 360002164538 and community post 15169243894685 |
| Moises: chords, key, lyric transcription, capo mode. US Premium $5.99/mo or $39.99/yr. | App Store id1515796612 (checked in this session) |
| Standalone song-tuning detectors exist (upload-based estimates of tuning family / pitch offset). **The novelty is integrating tuning detection, not the detection itself.** | giraldomedia.com/song-tuning-detector · 29a.ch/fix-tuning |

### 1.3 Platform facts

| Fact | Source |
|---|---|
| Document Picture-in-Picture (an always-on-top HTML window) works in Chrome/Edge 116+ and Firefox 151+. It is unsupported in Safari, Chrome for Android and Firefox for Android. | developer.chrome.com/docs/web-platform/document-picture-in-picture · openpwa.net reference (MDN browser-compat-data) |
| Android 10+ `AudioPlaybackCapture` needs a MediaProjection consent prompt. Apps can opt out via their capture policy. Reportedly, Spotify, Netflix and most apps with copy protection (DRM) opt out and capture as silence. | developer.android.com/media/platform/av-capture · visioforge.com guide (third-party claim) |
| iOS has no cross-app overlay. System-audio capture is possible only through ReplayKit broadcast extensions, and audio from copy-protected apps (Apple Music) is reported silent. | developer.apple.com/forums/tags/replaykit · github.com/maksymenkoyr/sine-visuals-lab/issues/414 (third-party) |
| The Web Speech API accepts a `MediaStreamTrack` (`start(track)`). `processLocally` (on-device recognition) shipped in Chrome 139. The default path sends audio to the vendor. | MDN SpeechRecognition.start · micdrop.dev/blog/web-speech-api |
| LRCLIB allows any origin (CORS) and has `Lrclib-Client` on its header allow-list. | Verified in LRCLIB's server source (`server/src/router.rs`, github.com/tranxuanthang/lrclib) |

### 1.4 Legal facts

| Fact | Source |
|---|---|
| *Thaler v. Perlmutter*: cert denied 2026-03-02 (No. 25-449). Human authorship is required. The Copyright Office says prompting alone is not enough for the AI-generated portion. | hklaw.com (2026-03) · casrai.org summary |
| Lyrics for streaming services are licensed through LyricFind and Musixmatch. Their antitrust litigation over Musixmatch's exclusive Warner Chappell deal shows the supply is concentrated. | caselaw.findlaw.com (LyricFind v. Musixmatch, N.D. Cal. 2025) |
| Musixmatch API terms allow non-commercial use only, unless Musixmatch approves in writing. | about.musixmatch.com/apiterms |
| The core Shazam landmark-fingerprint patent US 6,990,453 is shown as "Expired – Lifetime" (adjusted expiration 2024-01-07). Google Patents notes this is not a legal analysis. | patents.google.com/patent/US6990453B2 |

---

## 2. Vulnerability breakdown (red team)

| # | Vulnerability | Failure mode | Severity | Hardening (done / next) |
|---|---|---|---|---|
| V1 | **iOS platform** | No overlay and no other-app audio, so "overlays whenever music is played" is impossible on iPhone | High | Done: microphone path; Help explains it. Next: market it as "second screen next to the speaker". |
| V2 | **Android platform** | A web app is microphone-only. A native app with playback capture still gets silence from DRM apps. | High | Next: Capacitor/TWA wrapper with overlay permission. Capture where allowed, microphone otherwise. |
| V3 | **Background listening** | A closed tab can't listen, so users expect magic that browsers forbid | Medium | Done: auto-segmentation of playlists, pop-out window, wake-lock. Next: native shell. |
| V4 | **Chord accuracy on dense mixes** | Wrong chords → loss of trust. Accuracy is unmeasured on commercial audio. | High | Next: evaluate on an annotated dataset; "check by ear" copy is in place; optional ML model (v2). |
| V5 | **Tuning inference ambiguity** | Bass + guitar fake a low "stack"; capo vs retune is ambiguous | Medium | Done: calibrated probabilities (90% demo, 41–54% real "best guess"), alternatives, "Standard + capo X". |
| V6 | **Cold start** | Only knows songs it has heard. Incumbents know millions (Chordify via YouTube). | High (business) | Next: optional shared song maps keyed by fingerprint. That raises V7/V8. |
| V7 | **Lyrics licensing** | LRCLIB is community data. Commercial display needs LyricFind/Musixmatch licences, and costs are unknown. | High (legal) | Done: lyrics are user-initiated, personal use, attributed. Next: get quotes, or ship "paste your own". |
| V8 | **Copyright on stored analysis** | Chord progressions are generally not protectable, but lyrics are. Sharing sheets at scale invites takedowns. | Medium | Done: no audio stored; lyrics stay on the device. Next: keep sharing chords-only unless licensed. |
| V9 | **Weak code moat** | AI-written code has thin copyright and is easy for competitors to copy | Medium | Next: the moat is brand, data (song maps), distribution and human design choices. Document human contributions. |
| V10 | **Partnership** | 51/49 on an idea-only contribution. No vesting, roles or IP assignment. Ties broken by a 51% holder. | High (governance) | Next: written operating agreement before any spend ([RESEARCH VECTOR] counsel). |
| V11 | **Privacy** | Speech recognition may send audio to the browser vendor. Lyric lookups reveal titles to LRCLIB. | Low–Medium | Done: on-device by default; both are opt-in and disclosed in Help. |
| V12 | **Repo hygiene** | A commercial app sits inside a civic-transparency repo, which blurs ownership and licensing | Medium | Done: self-contained folder, liftable. Next: move it to its own repo (owner action). |

---

## 3. Probabilistic outcome matrix

These are **judgement estimates**, not measurements. They assume v0.1 as it stands, then the next steps listed in §4.

| Scenario | 0–3 months | 3–6 months | 6–12 months | Key driver |
|---|---|---|---|---|
| A. Works well as Dennis's / the band's personal tool (PWA, microphone) | 70% | 75% | 75% | Real-room recognition (strong in tests) and chord accuracy on their songs (unknown) |
| B. Public free PWA reaches >1,000 monthly users | 5% | 15% | 25% | Distribution, not tech: musician communities, YouTube demos |
| C. Paid native app reaches $1k/month recurring revenue | <2% | 4% | 8% | Native overlay/capture, a lyrics licence, differentiation that survives copying |
| D. Lyrics or copyright complaint, if shipped publicly with LRCLIB lyrics at scale | 2% | 8% | 15% | Scale and visibility; mitigated by personal-use / chords-only sharing |
| E. Partnership dispute (no written agreement) | 10% | 20% | 30% | Expectation gap ("is it done?") plus undefined roles and money |
| F. An incumbent ships tuning detection or printing with lyrics | 10% | 20% | 35% | Low technical barrier; licensing is their constraint too |

### Second-order effects

- **0–3 months**
  - Real-device tests expose accuracy limits on dense mixes. Dennis's mental model ("it overlays whenever music plays") collides with iOS rules.
  - Without a written split, the first real cost (developer accounts, a lyrics quote) triggers the ownership conversation under pressure.
- **3–6 months**
  - If public, the users who stay are those who value privacy and offline use and the print-with-words sheet.
  - Requests for "songs it already knows" push toward shared song maps. That is a moat if it works, and a liability for lyrics and moderation.
- **6–12 months**
  - Either a niche tool (bands, teachers, worship teams with printed sets), or a pivot to B2B: a white-label "learn our set list" tool for cover bands and churches. B2B sidesteps cold start because the customer supplies the songs.

### Incentive model (low-trust)

- **Dennis:** maximise share and control for the idea; minimise his own spend. A 51% stake gives control without capital or code.
- **Charlie:** wants the owner role, the build and the hosting. He bears the execution risk and the account liability (repo, keys, stores).
- **Platforms and rights holders:** incentivised to block capture (DRM) and to monetise lyrics, so there is structural friction against the "overlay anything" vision.
- **Incumbents:** will copy any feature that shows traction. Their own lyrics-licensing constraints are a partial shield for a print-with-words feature only if TuneAlong licenses lyrics as well.
- **Implication:** tie equity to *contributions that can't be copied* — distribution, users, data, licensing deals, capital — and to vesting over time. Do not tie it to the idea or to code that an AI can regenerate.

---

## 4. Recommended next steps (owner decisions)

1. **This week:** test on a real Android phone and an iPhone near a speaker, and desktop Chrome with tab audio, with 10–20 real songs.
   - Record recognition rate and time-to-recognise.
   - Have a guitarist mark chord errors.
2. **Before any spend:** a written agreement between Dennis and Charlie covering:
   - contributions;
   - vesting (e.g. 4 years with a 1-year cliff);
   - decision rights and deadlock handling;
   - IP assignment to an entity;
   - expense handling and exit.
3. **Hosting:** move `tune-along/` to its own repository and deploy `dist/` as a static site (GitHub Pages / Netlify / Cloudflare). Requires your approval.
4. **Lyrics:** keep lyrics personal-use (LRCLIB lookup or paste) until a licence quote exists. Public sharing should be chords-only.
5. **v0.2 options:**
   - Android wrapper with overlay and playback capture;
   - beat-synchronous chord grid;
   - melody/riff notes via an on-device transcription model;
   - shared, fingerprint-keyed chord maps — chords only.

---

## 5. Research vectors (below the 95% confidence bar — not asserted)

- **[RESEARCH VECTOR]** Lyrics licence cost for a ~1k–10k-user app. Request quotes: LyricFind (lyricfind.com), Musixmatch Pro/Enterprise (about.musixmatch.com/business).
- **[RESEARCH VECTOR]** Trademark clearance for "TUNEALONG", "TUNE ALONG" and "PLAY ALONG" in classes 9/41/42. Search USPTO (tmsearch.uspto.gov). No conflict appeared in a web search, but that is not clearance.
- **[RESEARCH VECTOR]** Freedom-to-operate (whether any live patent blocks this) beyond US 6,990,453. Search Google Patents for active audio-fingerprint / chord-recognition claims (CPC G06F16/683, G10H2210/571), or ask counsel.
- **[RESEARCH VECTOR]** Can iOS 27 ScreenCaptureKit capture other apps' audio, and what about copy-protected (DRM) audio? Check Apple's "Capturing screen content on iOS" docs and test on a device.
- **[RESEARCH VECTOR]** Which Android music apps opt out of playback capture (Spotify, YouTube Music, Pandora, Apple Music for Android)? Test on a device with a capture probe app.
- **[RESEARCH VECTOR]** Chord accuracy on commercial music. Evaluate against annotated datasets (e.g. Isophonics, McGill Billboard), with legally obtained audio.
- **[RESEARCH VECTOR]** Does Chord ai *detect a song's tuning*, or only offer alternate-tuning chord libraries? Check its release notes and test the app.
- **[RESEARCH VECTOR]** Wyoming entity and operating-agreement terms for a 51/49 member split, with deadlock and vesting provisions. Ask a Wyoming business attorney.

---

## [KNOWLEDGE BULLET]

`TuneAlong v0.1 (2026-10-28)`: an on-device PWA in `therealwindycity/tune-along`.

- **Learns, recognises, prints:**
  - learns a song once: chords (Viterbi over templates), key, BPM, A-reference (±1¢ on synthetic audio), tuning (calibrated probabilities);
  - recognises it again in about 3–4 s, exact position, using landmark hashes at 11,025 Hz;
  - shows next-chord, synced lyrics (LRCLIB) and a print sheet with words.
- **Tests:**
  - 49 unit/e2e tests;
  - 8/8 headless-Chrome checks;
  - 10/10 real-recording recognitions, 0 false positives.
- **Not deployed.** Not tried on phones. Chord accuracy on commercial audio is unmeasured.
- **Market:** crowded (Chord ai $69.99/yr, Chordify $42–54/yr, Moises $39.99/yr).
- **Edge:** tuning at the intro, offline/private, print with lyrics (Chordify's print excludes lyrics).
- **Blockers:**
  - iOS: no overlay or other-app audio;
  - Android: native app needed and DRM apps opt out of capture;
  - lyrics need LyricFind/Musixmatch licences;
  - AI code has thin copyright (Thaler cert denied 2026-03-02).
- **Partnership:** 51/49 needs a written agreement with vesting and IP assignment before any spend.
- **Next:** real-device test, then the agreement, then a separate repo and static deploy (needs approval).
