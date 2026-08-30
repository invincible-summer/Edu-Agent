/**
 * Voice capture worklet: mic -> mono -> 16 kHz -> PCM16 frames.
 *
 * Runs on the AudioWorklet rendering thread; posts Int16Array chunks
 * (~10 ms of audio) to the main thread, which forwards them verbatim over
 * the voice WebSocket (protocol: backend/app/api/v1/voice.py). No external
 * dependency — served as a static asset from /voice-pcm-worklet.js.
 */
class VoicePcmDownsampler extends AudioWorkletProcessor {
  constructor() {
    super();
    this.targetRate = 16000;
    this.ratio = sampleRate / this.targetRate; // e.g. 48000 / 16000 = 3
    this.pos = 0;          // fractional input position within one output step
    this.acc = 0;          // running sum for box-average
    this.accN = 0;
    this.out = [];         // completed output samples awaiting a batch post
    this.mono = new Float32Array(128);
  }

  process(inputs) {
    const input = inputs[0];
    if (!input || input.length === 0 || !input[0]) return true;
    const ch0 = input[0];
    const nch = input.length;
    const len = ch0.length;
    if (this.mono.length < len) this.mono = new Float32Array(len);
    const mono = this.mono;
    for (let i = 0; i < len; i++) {
      if (nch === 1) {
        mono[i] = ch0[i];
      } else {
        let acc = 0;
        for (let c = 0; c < nch; c++) acc += input[c][i];
        mono[i] = acc / nch;
      }
      this.acc += mono[i];
      this.accN += 1;
      this.pos += 1;
      if (this.pos >= this.ratio) {
        this.out.push(this.accN > 0 ? this.acc / this.accN : 0);
        this.pos -= this.ratio;
        this.acc = 0;
        this.accN = 0;
      }
    }
    // Batch ~10 ms (160 samples) so the WS frame rate stays near 100/s max.
    if (this.out.length >= 160) {
      const n = this.out.length;
      const pcm = new Int16Array(n);
      for (let i = 0; i < n; i++) {
        let v = Math.round(this.out[i] * 32767);
        if (v > 32767) v = 32767;
        else if (v < -32768) v = -32768;
        pcm[i] = v;
      }
      this.out.length = 0;
      this.port.postMessage(pcm, [pcm.buffer]);
    }
    return true;
  }
}

registerProcessor("voice-pcm", VoicePcmDownsampler);
