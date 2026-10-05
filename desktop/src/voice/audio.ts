// Pure audio helpers: WAV packing for the speech recogniser and a voice activity segmenter that
// cuts a live stream of microphone samples into spoken utterances.

export const SAMPLE_RATE = 16000;

// 16-bit mono PCM as a WAV file (what whisper.cpp reads).
export function pcmToWav(samples: Int16Array, sampleRate = SAMPLE_RATE): Uint8Array {
  const bytes = samples.length * 2;
  const out = new Uint8Array(44 + bytes);
  const view = new DataView(out.buffer);
  const text = (offset: number, value: string) => {
    for (let i = 0; i < value.length; i++) out[offset + i] = value.charCodeAt(i);
  };
  text(0, "RIFF");
  view.setUint32(4, 36 + bytes, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true); // size of the format block
  view.setUint16(20, 1, true); // PCM
  view.setUint16(22, 1, true); // mono
  view.setUint32(24, sampleRate, true);
  view.setUint32(28, sampleRate * 2, true); // bytes per second
  view.setUint16(32, 2, true); // bytes per sample
  view.setUint16(34, 16, true); // bits per sample
  text(36, "data");
  view.setUint32(40, bytes, true);
  new Int16Array(out.buffer, 44, samples.length).set(samples);
  return out;
}

export function rms(frame: Int16Array): number {
  if (frame.length === 0) return 0;
  let sum = 0;
  for (let i = 0; i < frame.length; i++) sum += (frame[i] as number) * (frame[i] as number);
  return Math.sqrt(sum / frame.length) / 32768;
}

export interface SegmenterOptions {
  frameMs: number; // the size of the frames that are fed in
  minRms: number; // below this a frame is never speech (a very quiet room is still not silent)
  speechOverNoise: number; // a frame is speech when this many times louder than the room
  startFrames: number; // this many loud frames in a row begin an utterance
  hangMs: number; // this much quiet ends it
  prerollMs: number; // kept from before the start (the first syllable is quiet)
  minSpeechMs: number; // shorter than this is a click or a cough
  maxMs: number; // longer than this is cut (speech from a video, not a request)
}

export const DEFAULT_SEGMENTER: SegmenterOptions = {
  frameMs: 30,
  minRms: 0.006,
  speechOverNoise: 4,
  startFrames: 4,
  hangMs: 1000,
  prerollMs: 300,
  minSpeechMs: 350,
  maxMs: 15000,
};

export type SegmenterEvent =
  | { type: "start" } // someone began to speak
  | { type: "utterance"; pcm: Int16Array; speechMs: number }
  | { type: "dropped"; reason: "too short" | "too long" };

// Feed fixed size frames; returns what happened. The loudness of the room is learnt while
// nothing is being said, so a fan or a distant video does not count as speech.
export class Segmenter {
  private noise = 0.004;
  private preroll: Int16Array[] = [];
  private current: Int16Array[] = [];
  private loud = 0;
  private quietFrames = 0;
  private speaking = false;
  private speechFrames = 0;

  constructor(private readonly options: SegmenterOptions = DEFAULT_SEGMENTER) {}

  get isSpeaking(): boolean {
    return this.speaking;
  }

  // Forget what is being heard (the microphone was closed for a moment).
  reset(): void {
    this.preroll = [];
    this.current = [];
    this.loud = 0;
    this.quietFrames = 0;
    this.speaking = false;
    this.speechFrames = 0;
  }

  push(frame: Int16Array): SegmenterEvent[] {
    const o = this.options;
    const level = rms(frame);
    const isSpeech = level >= Math.max(o.minRms, this.noise * o.speechOverNoise);
    const events: SegmenterEvent[] = [];
    const maxPreroll = Math.ceil(o.prerollMs / o.frameMs);

    if (!this.speaking) {
      // Learn the room: slowly up, quickly down.
      if (!isSpeech) this.noise = this.noise * 0.95 + level * 0.05;
      this.preroll.push(frame);
      if (this.preroll.length > maxPreroll + o.startFrames) this.preroll.shift();
      this.loud = isSpeech ? this.loud + 1 : 0;
      if (this.loud >= o.startFrames) {
        this.speaking = true;
        this.current = [...this.preroll];
        this.preroll = [];
        this.quietFrames = 0;
        this.speechFrames = this.loud;
        events.push({ type: "start" });
      }
      return events;
    }

    this.current.push(frame);
    if (isSpeech) {
      this.speechFrames += 1;
      this.quietFrames = 0;
    } else {
      this.quietFrames += 1;
    }
    const length = this.current.length * o.frameMs;
    const finished = this.quietFrames * o.frameMs >= o.hangMs;
    if (finished || length >= o.maxMs) {
      const speechMs = this.speechFrames * o.frameMs;
      const kept = finished ? this.current.slice(0, this.current.length - Math.max(0, this.quietFrames - 3)) : this.current;
      this.speaking = false;
      this.loud = 0;
      this.current = [];
      this.speechFrames = 0;
      if (!finished) events.push({ type: "dropped", reason: "too long" });
      else if (speechMs < o.minSpeechMs) events.push({ type: "dropped", reason: "too short" });
      else events.push({ type: "utterance", pcm: join(kept), speechMs });
    }
    return events;
  }
}

function join(frames: Int16Array[]): Int16Array {
  const total = frames.reduce((n, f) => n + f.length, 0);
  const out = new Int16Array(total);
  let at = 0;
  for (const f of frames) {
    out.set(f, at);
    at += f.length;
  }
  return out;
}

// 16-bit mono PCM and its sample rate from a WAV file (what Piper writes).
export function parseWav(bytes: Uint8Array): { pcm: Int16Array; sampleRate: number } {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const tag = (at: number) => String.fromCharCode(bytes[at] as number, bytes[at + 1] as number, bytes[at + 2] as number, bytes[at + 3] as number);
  if (bytes.length < 12 || tag(0) !== "RIFF" || tag(8) !== "WAVE") throw new Error("not a WAV file");
  let sampleRate = SAMPLE_RATE;
  let at = 12;
  while (at + 8 <= bytes.length) {
    const size = view.getUint32(at + 4, true);
    if (tag(at) === "fmt ") {
      sampleRate = view.getUint32(at + 12, true);
      if (view.getUint16(at + 10, true) !== 1 || view.getUint16(at + 22, true) !== 16) throw new Error("only 16-bit mono WAV is supported");
    } else if (tag(at) === "data") {
      const start = at + 8;
      const length = Math.min(size, bytes.length - start) & ~1;
      const pcm = new Int16Array(length / 2);
      for (let i = 0; i < pcm.length; i++) pcm[i] = view.getInt16(start + i * 2, true);
      return { pcm, sampleRate };
    }
    at += 8 + size + (size % 2);
  }
  throw new Error("the WAV file has no audio");
}

