/** Tempo (BPM) from an onset-strength envelope via autocorrelation with a tempo prior. */

export function estimateTempo(onset: ArrayLike<number>, frameRate: number, minBpm = 55, maxBpm = 210): { bpm: number; confidence: number } | null {
  const n = onset.length;
  if (n < frameRate * 6) return null;
  // high-pass: subtract a ~1 s moving average, half-wave rectify
  const win = Math.max(3, Math.round(frameRate));
  const env = new Float32Array(n);
  let acc = 0;
  const pre = new Float64Array(n + 1);
  for (let i = 0; i < n; i++) { acc += onset[i]; pre[i + 1] = acc; }
  for (let i = 0; i < n; i++) {
    const a = Math.max(0, i - win), b = Math.min(n, i + win + 1);
    const mean = (pre[b] - pre[a]) / (b - a);
    env[i] = Math.max(0, onset[i] - mean);
  }
  const minLag = Math.floor((60 * frameRate) / maxBpm);
  const maxLag = Math.ceil((60 * frameRate) / minBpm);
  if (maxLag >= n / 2) return null;
  const ac = new Float64Array(maxLag + 2);
  let zero = 0;
  for (let i = 0; i < n; i++) zero += env[i] * env[i];
  if (zero <= 0) return null;
  for (let lag = minLag - 1; lag <= maxLag + 1; lag++) {
    let s = 0;
    for (let i = 0; i + lag < n; i++) s += env[i] * env[i + lag];
    ac[lag] = s / (n - lag);
  }
  let bestLag = -1, bestScore = -Infinity, bestRaw = 0;
  for (let lag = minLag; lag <= maxLag; lag++) {
    const bpm = (60 * frameRate) / lag;
    // log-normal prior centred on 115 BPM; also reward support at 2× lag (the bar-level pulse)
    const prior = Math.exp(-0.5 * (Math.log2(bpm / 115) / 0.9) ** 2);
    const support = lag * 2 <= maxLag + 1 ? 0.5 * ac[lag * 2] : 0;
    const score = (ac[lag] + support) * prior;
    if (score > bestScore && ac[lag] >= ac[lag - 1] && ac[lag] >= ac[lag + 1]) {
      bestScore = score; bestLag = lag; bestRaw = ac[lag];
    }
  }
  if (bestLag < 0) return null;
  const y0 = ac[bestLag - 1], y1 = ac[bestLag], y2 = ac[bestLag + 1];
  const den = y0 - 2 * y1 + y2;
  const refined = Math.abs(den) > 1e-12 ? bestLag + (0.5 * (y0 - y2)) / den : bestLag;
  return { bpm: (60 * frameRate) / refined, confidence: Math.min(1, bestRaw / (zero / n)) };
}
