/*
 * TuneAlong capture worklet: mixes the input to mono and posts fixed-size chunks to
 * the analysis worker through a MessagePort. When the input goes away (a file
 * finished playing) it keeps posting silence so the engine can notice the song ended.
 */
class CaptureProcessor extends AudioWorkletProcessor {
  constructor(options) {
    super();
    const opts = (options && options.processorOptions) || {};
    this.chunk = opts.chunkSize || 2048;
    this.buf = new Float32Array(this.chunk);
    this.n = 0;
    this.out = null;
    this.alive = true;
    this.port.onmessage = (e) => {
      if (e.data && e.data.type === 'port') this.out = e.data.port;
      if (e.data && e.data.type === 'stop') this.alive = false;
    };
  }

  process(inputs) {
    const input = inputs[0];
    const frames = input && input.length ? input[0].length : 128;
    const chs = input ? input.length : 0;
    for (let i = 0; i < frames; i++) {
      let s = 0;
      for (let c = 0; c < chs; c++) s += input[c][i];
      this.buf[this.n++] = chs ? s / chs : 0;
      if (this.n === this.chunk) {
        const target = this.out || this.port;
        target.postMessage(this.buf, [this.buf.buffer]);
        this.buf = new Float32Array(this.chunk);
        this.n = 0;
      }
    }
    return this.alive;
  }
}

registerProcessor('tunealong-capture', CaptureProcessor);
