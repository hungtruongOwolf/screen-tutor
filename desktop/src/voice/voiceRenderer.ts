// Runs in the voice window: listens to the microphone, cuts the stream into utterances and sends
// them to the main process; speaks what the main process asks for; draws the orb.

import { SAMPLE_RATE, Segmenter } from "./audio";
import { explainMicError, openMicStream } from "./micAccess";
import type { VoiceEvent, VoiceMessage } from "./protocol";

declare global {
  interface Window {
    voiceApi: {
      onMessage(callback: (message: VoiceMessage) => void): void;
      send(event: VoiceEvent): void;
    };
  }
}

const api = window.voiceApi;
const pill = document.getElementById("pill") as HTMLElement;
const orb = document.getElementById("orb") as HTMLElement;
const mainLine = document.getElementById("main") as HTMLElement;
const subLine = document.getElementById("sub") as HTMLElement;

orb.addEventListener("click", () => api.send({ kind: "toggle-mute" }));

function show(state: string, main: string, sub = ""): void {
  pill.className = `pill ${state}`;
  mainLine.textContent = main;
  subLine.textContent = sub;
  subLine.style.display = sub ? "block" : "none";
}

// ---- the microphone ------------------------------------------------------------------------

const FRAME = 480; // 30 ms at 16 kHz
const segmenter = new Segmenter();
let open = true;
let pending = new Int16Array(0);
let lastLevel = 0;

function handleSamples(input: Float32Array): void {
  const samples = new Int16Array(input.length);
  for (let i = 0; i < input.length; i++) {
    const v = Math.max(-1, Math.min(1, input[i] as number));
    samples[i] = Math.round(v * 32767);
  }
  const merged = new Int16Array(pending.length + samples.length);
  merged.set(pending, 0);
  merged.set(samples, pending.length);
  let at = 0;
  for (; at + FRAME <= merged.length; at += FRAME) {
    const frame = merged.slice(at, at + FRAME);
    if (!open) continue;
    for (const event of segmenter.push(frame)) {
      if (event.type === "start") api.send({ kind: "speech-start" });
      else if (event.type === "utterance") {
        const copy = event.pcm.slice();
        api.send({ kind: "utterance", pcm: copy.buffer });
      }
    }
    // the loudness, ten times a second, so the orb can breathe with the voice
    let sum = 0;
    for (const v of frame) sum += v * v;
    const level = Math.sqrt(sum / FRAME) / 32768;
    const now = performance.now();
    if (now - lastLevel > 100) {
      lastLevel = now;
      api.send({ kind: "level", value: level });
    }
  }
  pending = merged.slice(at);
}

// The list of voices is filled in a moment after the page loads.
function voicesReady(): Promise<SpeechSynthesisVoice[]> {
  if (speechSynthesis.getVoices().length > 0) return Promise.resolve(speechSynthesis.getVoices());
  return new Promise((resolve) => {
    const timer = setTimeout(() => resolve(speechSynthesis.getVoices()), 2000);
    speechSynthesis.onvoiceschanged = () => {
      // The first change can still be an empty list.
      if (speechSynthesis.getVoices().length === 0) return;
      clearTimeout(timer);
      resolve(speechSynthesis.getVoices());
    };
  });
}

let audioContext: AudioContext | undefined;
let retry: ReturnType<typeof setTimeout> | undefined;

function closeMicrophone(): void {
  void audioContext?.close().catch(() => undefined);
  audioContext = undefined;
  segmenter.reset();
  pending = new Int16Array(0);
}

function retryLater(ms: number): void {
  if (retry) clearTimeout(retry);
  retry = setTimeout(() => void startMicrophone(), ms);
}

async function startMicrophone(): Promise<void> {
  if (retry) clearTimeout(retry);
  retry = undefined;
  closeMicrophone();
  const began = performance.now();
  try {
    const stream = await openMicStream(navigator.mediaDevices);
    const track = stream.getAudioTracks()[0];
    const context = new AudioContext({ sampleRate: SAMPLE_RATE });
    audioContext = context;
    const source = context.createMediaStreamSource(stream);
    const processor = context.createScriptProcessor(2048, 1, 1);
    processor.onaudioprocess = (event) => handleSamples(event.inputBuffer.getChannelData(0));
    source.connect(processor);
    processor.connect(context.destination); // silent: nothing is written to the output
    // Unplugged or taken away: try again.
    track?.addEventListener("ended", () => {
      api.send({ kind: "mic-error", detail: "The microphone was disconnected. Looking for it again." });
      retryLater(1500);
    });
    const voices = await voicesReady();
    api.send({
      kind: "ready",
      voices: [`opened ${track?.label ?? "a microphone"} in ${Math.round(performance.now() - began)} ms`, ...voices.map((v) => `${v.name} (${v.lang})`)],
    });
  } catch (error) {
    api.send({ kind: "mic-error", detail: explainMicError(error) });
    retryLater(8000); // a headset may be plugged in, a setting changed
  }
}

// A microphone appears or goes: look again.
navigator.mediaDevices.addEventListener("devicechange", () => {
  if (!audioContext) retryLater(500);
});

// ---- speaking ------------------------------------------------------------------------------

function pickVoice(name?: string): SpeechSynthesisVoice | undefined {
  const voices = speechSynthesis.getVoices();
  const english = voices.filter((v) => v.lang.toLowerCase().startsWith("en"));
  return (
    (name ? voices.find((v) => v.name.toLowerCase().includes(name.toLowerCase())) : undefined) ??
    english.find((v) => /natural|aria|jenny/i.test(v.name)) ??
    english.find((v) => /zira/i.test(v.name)) ??
    english[0] ??
    voices[0]
  );
}

// Long texts are spoken a sentence at a time (the speech engine of Chromium can stall on a long one).
function sentences(text: string): string[] {
  return text.match(/[^.!?;:]+[.!?;:]*\s*/g)?.map((s) => s.trim()).filter(Boolean) ?? [text];
}

let speaking = 0; // the id of what is being spoken

function speak(id: number, text: string, voiceName?: string, rate = 1.2): void {
  speechSynthesis.cancel();
  speaking = id;
  const parts = sentences(text);
  const voice = pickVoice(voiceName);
  const done = () => {
    if (speaking === id) {
      speaking = 0;
      api.send({ kind: "speak-end", id });
    }
  };
  if (parts.length === 0) {
    done();
    return;
  }
  parts.forEach((part, index) => {
    const utterance = new SpeechSynthesisUtterance(part);
    if (voice) utterance.voice = voice;
    utterance.rate = rate;
    utterance.onend = () => {
      if (index === parts.length - 1) done();
    };
    utterance.onerror = () => {
      if (index === parts.length - 1) done();
    };
    speechSynthesis.speak(utterance);
  });
}

// Audio made by Piper, played one piece after another without gaps.
let playback: AudioContext | undefined;
let playHead = 0;
const playing = new Set<AudioBufferSourceNode>();

function playChunk(id: number, pcm: ArrayBuffer, sampleRate: number, last: boolean): void {
  if (speaking !== id) {
    speechSynthesis.cancel();
    speaking = id;
  }
  playback ??= new AudioContext();
  void playback.resume();
  const samples = new Int16Array(pcm);
  const floats = new Float32Array(samples.length);
  for (let i = 0; i < samples.length; i++) floats[i] = (samples[i] as number) / 32768;
  const buffer = playback.createBuffer(1, floats.length, sampleRate);
  buffer.copyToChannel(floats, 0);
  const source = playback.createBufferSource();
  source.buffer = buffer;
  source.connect(playback.destination);
  const at = Math.max(playback.currentTime + 0.03, playHead);
  source.start(at);
  playHead = at + buffer.duration;
  playing.add(source);
  source.onended = () => {
    playing.delete(source);
    if (last && speaking === id) {
      speaking = 0;
      api.send({ kind: "speak-end", id });
    }
  };
}

function cancelSpeech(): void {
  const id = speaking;
  speaking = 0;
  for (const source of playing) {
    source.onended = null;
    try {
      source.stop();
    } catch {
      // already finished
    }
  }
  playing.clear();
  playHead = 0;
  speechSynthesis.cancel();
  if (id) api.send({ kind: "speak-end", id });
}

// ---- messages from the main process -------------------------------------------------------------

api.onMessage((message) => {
  switch (message.type) {
    case "start-mic":
      void startMicrophone();
      break;
    case "retry-mic":
      void startMicrophone();
      break;
    case "gate":
      open = message.open;
      if (!open) {
        segmenter.reset();
        pending = new Int16Array(0);
      }
      break;
    case "speak":
      speak(message.id, message.text, message.voice, message.rate);
      break;
    case "play":
      playChunk(message.id, message.pcm, message.sampleRate, message.last);
      break;
    case "cancel-speech":
      cancelSpeech();
      break;
    case "ui":
      show(message.state, message.main, message.sub);
      break;
  }
});

// The ring follows the voice: the level is sent back by the main process as part of the state, but
// a quick local reaction looks better.
