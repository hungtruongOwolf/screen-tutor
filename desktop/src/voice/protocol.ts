// What the voice window and the main process say to each other.

export type OrbState = "starting" | "listening" | "hearing" | "thinking" | "speaking" | "muted" | "error";

// main -> voice window
export type VoiceMessage =
  | { type: "start-mic" }
  | { type: "retry-mic" }
  | { type: "gate"; open: boolean } // false: the microphone is not listened to (the tutor is talking)
  | { type: "speak"; id: number; text: string; voice?: string; rate?: number }
  | { type: "play"; id: number; pcm: ArrayBuffer; sampleRate: number; last: boolean } // audio made by Piper
  | { type: "cancel-speech" }
  | { type: "ui"; state: OrbState; main: string; sub?: string };

// voice window -> main
export type VoiceEvent =
  | { kind: "ready"; voices: string[] }
  | { kind: "utterance"; pcm: ArrayBuffer }
  | { kind: "speech-start" }
  | { kind: "level"; value: number }
  | { kind: "speak-end"; id: number }
  | { kind: "mic-error"; detail: string }
  | { kind: "toggle-mute" };
