// Short interface sounds, synthesised with the Web Audio API: no audio files to ship, and quiet by design.
// Turned on or off in the header (saved in ui.json).

let ctx: AudioContext | null = null;
let enabled = true;

export function setSoundsEnabled(on: boolean) {
  enabled = on;
}

function audio(): AudioContext | null {
  try {
    ctx ??= new AudioContext();
    if (ctx.state === 'suspended') void ctx.resume();
    return ctx;
  } catch {
    return null;
  }
}

/** One soft note: a sine with a fast attack and an exponential fade. */
function note(freq: number, at: number, length: number, volume = 0.07, type: OscillatorType = 'sine') {
  const a = audio();
  if (!a) return;
  const start = a.currentTime + at;
  const osc = a.createOscillator();
  const gain = a.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, start);
  gain.gain.setValueAtTime(0.0001, start);
  gain.gain.exponentialRampToValueAtTime(volume, start + 0.012);
  gain.gain.exponentialRampToValueAtTime(0.0001, start + length);
  osc.connect(gain).connect(a.destination);
  osc.start(start);
  osc.stop(start + length + 0.05);
}

export const sound = {
  /** A run finished with results, drafts were saved, keys passed the test. */
  success() {
    if (!enabled) return;
    note(659.25, 0, 0.22);
    note(830.61, 0.09, 0.22);
    note(987.77, 0.18, 0.42);
  },
  /** Something finished that needs a look, but nothing went wrong. */
  notify() {
    if (!enabled) return;
    note(880, 0, 0.18, 0.06);
    note(1174.66, 0.11, 0.3, 0.05);
  },
  /** A run failed or an action was refused. */
  error() {
    if (!enabled) return;
    note(311.13, 0, 0.2, 0.07, 'triangle');
    note(233.08, 0.14, 0.34, 0.07, 'triangle');
  },
  /** A small click for copy and toggles. */
  tap() {
    if (!enabled) return;
    note(1567.98, 0, 0.05, 0.035);
  },
};
