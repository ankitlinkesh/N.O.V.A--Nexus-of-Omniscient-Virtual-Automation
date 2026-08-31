// Web Audio waveform tap for the orb. One shared AudioContext + AnalyserNode.
// The Piper TTS <audio> element (created in app.js speakWithPiper) is routed
// through the analyser so the orb can pulse to the *real* voice while speaking.
// Everything is native browser API — nothing to install, nothing external.

let ctx = null;
let analyser = null;
let data = null;
const attached = new WeakSet();
let rafId = 0;

function ensure() {
  if (ctx) return;
  const AC = window.AudioContext || window.webkitAudioContext;
  if (!AC) return;
  ctx = new AC();
  analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  analyser.smoothingTimeConstant = 0.8;
  analyser.connect(ctx.destination);
  data = new Uint8Array(analyser.fftSize);
}

// Route an <audio> element through the analyser. Safe to call once per element;
// a MediaElementSource can only be created once, so we guard with a WeakSet.
export function attachElement(audioEl) {
  ensure();
  if (!ctx || !audioEl || attached.has(audioEl)) return;
  try {
    const src = ctx.createMediaElementSource(audioEl);
    src.connect(analyser);
    attached.add(audioEl);
    if (ctx.state === "suspended") ctx.resume().catch(() => {});
  } catch (err) {
    console.warn("[OrbAudio] could not tap audio element", err);
  }
}

// Begin feeding RMS level (0..1) to cb every frame. Returns a stop() function;
// startMeter also auto-replaces any prior meter.
export function startMeter(cb) {
  stopMeter();
  if (!analyser) { return stopMeter; }
  const loop = () => {
    analyser.getByteTimeDomainData(data);
    let sum = 0;
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128;
      sum += v * v;
    }
    const rms = Math.sqrt(sum / data.length);
    // scale up (speech RMS is small) and clamp
    cb(Math.min(1, rms * 3.2));
    rafId = requestAnimationFrame(loop);
  };
  rafId = requestAnimationFrame(loop);
  return stopMeter;
}

export function stopMeter() {
  if (rafId) cancelAnimationFrame(rafId);
  rafId = 0;
}
