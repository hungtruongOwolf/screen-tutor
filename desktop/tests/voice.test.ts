import { describe, expect, it } from "vitest";
import { Segmenter, pcmToWav, rms, SAMPLE_RATE } from "../src/voice/audio";
import { afterEach } from "vitest";
import { configureWake, DEFAULT_WAKE_WORDS, routeUtterance, wakeLabel, type Context } from "../src/voice/intent";
import { speakable } from "../src/voice/speakable";

const idle: Context = { inConversation: false, taskActive: false };
const talking: Context = { inConversation: true, taskActive: false };
const task: Context = { inConversation: false, taskActive: true };

afterEach(() => configureWake(DEFAULT_WAKE_WORDS));

describe("the wake word", () => {
  it("is Sherpa by default", () => {
    expect(wakeLabel()).toBe("Sherpa");
    expect(routeUtterance("Hey Sherpa, where do I click?", idle)).toEqual({ kind: "ask", text: "where do I click?" });
  });

  it("accepts the ways Sherpa is misheard, even split in two", () => {
    for (const heard of ["Hey Sherper, where do I click?", "Hey Shirpa, where do I click?", "Hey sher pa, where do I click?", "Hey Sharper, where do I click?", "Hello Sherpa where do I click"]) {
      expect(routeUtterance(heard, idle).kind).toBe("ask");
    }
  });

  it("takes a near miss of a long word but not a different word", () => {
    expect(routeUtterance("Hey Sherpo, where do I click?", idle).kind).toBe("ask"); // a letter off a six letter word: accepted
    expect(routeUtterance("Hey Nick, where do I click?", idle).kind).toBe("ignore");
    expect(routeUtterance("the mountain guides carried the load all day long", idle).kind).toBe("ignore");
  });

  it("can be changed to any word, and the first one names it", () => {
    configureWake(["Jarvis"]);

    expect(wakeLabel()).toBe("Jarvis");
    expect(routeUtterance("Hey Jarvis, open the chat", idle)).toEqual({ kind: "command", command: "open-chat" });
    expect(routeUtterance("Hey Sherpa, where do I click?", idle).kind).toBe("ignore");
    expect(routeUtterance("Hey Jarvis", idle)).toEqual({ kind: "wake" });
  });

  it("does not let a three letter wake word match its near misses", () => {
    configureWake(["max"]);

    expect(routeUtterance("Hey Max, what is this?", idle).kind).toBe("ask");
    expect(routeUtterance("Hey Mac, what is this?", idle).kind).toBe("ignore");
  });

  it("falls back to the defaults when nothing usable is given", () => {
    configureWake(["", " "]);

    expect(wakeLabel()).toBe("Sherpa");
  });
});

describe("who an utterance is for", () => {
  it("answers a request that starts with the wake word, whichever way it is heard", () => {
    for (const heard of ["Hey Sherpa, I need an access key for my app.", "Hey Shirpa, I need an access key for my app.", "Okay sherpa I need an access key for my app."]) {
      expect(routeUtterance(heard, idle)).toEqual({ kind: "ask", text: "I need an access key for my app." });
    }
  });

  it("accepts a greeting or two before the wake word and a wake word heard close to Sherpa", () => {
    expect(routeUtterance("Hello, hey sherper, can you explain this", idle)).toEqual({ kind: "ask", text: "can you explain this" });
    expect(routeUtterance("Hello hello sherpa what is this", idle)).toEqual({ kind: "ask", text: "what is this" });
    expect(routeUtterance("Hey sharper, where do I click?", idle)).toEqual({ kind: "ask", text: "where do I click?" });
    expect(routeUtterance("Hey Shurpa", idle)).toEqual({ kind: "wake" });
  });

  it("does not take other names for the wake word", () => {
    expect(routeUtterance("Hey Sarah, where do I click?", idle).kind).toBe("ignore");
    expect(routeUtterance("Hello everyone and welcome to the video", idle).kind).toBe("ignore");
    expect(routeUtterance("The tutorial shows how to start", idle).kind).toBe("ignore");
  });

  it("is only listening when it hears the wake word alone", () => {
    expect(routeUtterance("Hey sherpa.", idle)).toEqual({ kind: "wake" });
    expect(routeUtterance("sherpa", idle)).toEqual({ kind: "wake" });
  });

  it("ignores speech that is not for it (a video, a conversation in the room)", () => {
    expect(routeUtterance("so the hypotenuse is the longest side of the triangle", idle).kind).toBe("ignore");
    expect(routeUtterance("What is next?", idle).kind).toBe("ignore");
  });

  it("ignores what recognisers write for silence and noise", () => {
    for (const heard of ["", "Thank you.", "[BLANK_AUDIO]", "(music)", "you", "Thanks for watching!", "*coughs*"]) {
      expect(routeUtterance(heard, talking).kind).toBe("ignore");
    }
  });

  it("takes follow-ups without the wake word while a conversation is going on", () => {
    expect(routeUtterance("Why is that true?", talking)).toEqual({ kind: "ask", text: "Why is that true?" });
  });

  it("takes the short things said during a task without the wake word", () => {
    expect(routeUtterance("Okay, I clicked it. What is next?", task).kind).toBe("ask");
    expect(routeUtterance("I don't see it", task).kind).toBe("ask");
    expect(routeUtterance("Done", task).kind).toBe("ask");
    expect(routeUtterance("the weather is nice today", task).kind).toBe("ignore");
  });
});

describe("commands", () => {
  const command = (text: string, context: Context = idle) => {
    const intent = routeUtterance(text, context);
    return intent.kind === "command" ? intent.command : intent.kind;
  };

  it("opens and closes the chat by voice, with or without the wake word", () => {
    expect(command("Open chat")).toBe("open-chat");
    expect(command("hey sherpa, open the chat window")).toBe("open-chat");
    expect(command("Show chat please")).toBe("open-chat");
    expect(command("Let me type")).toBe("open-chat");
    expect(command("I want to type")).toBe("open-chat");
    expect(command("Close chat")).toBe("close-chat");
    expect(command("hide the chat")).toBe("close-chat");
  });

  it("needs the wake word, a conversation or a task for the commands that could be said by accident", () => {
    expect(command("stop")).toBe("ignore");
    expect(command("next step")).toBe("ignore");
    expect(command("hey sherpa, stop")).toBe("stop");
    expect(command("stop", task)).toBe("stop");
    expect(command("next step", task)).toBe("next-step");
    expect(command("end the task", task)).toBe("stop");
  });

  it("understands the rest of the commands", () => {
    expect(command("hey sherpa new chat")).toBe("new-chat");
    expect(command("hey sherpa start over")).toBe("new-chat");
    expect(command("hey sherpa clear the marks")).toBe("clear-marks");
    expect(command("hey sherpa pause")).toBe("pause-following");
    expect(command("hey sherpa resume following")).toBe("resume-following");
    expect(command("hey sherpa go back")).toBe("previous-step");
    expect(command("hey sherpa say that again")).toBe("repeat");
    expect(command("hey sherpa be quiet")).toBe("quiet");
    expect(command("hey sherpa talk to me")).toBe("speak");
    expect(command("hey sherpa mute")).toBe("mute");
  });

  it("does not take a question for a command", () => {
    expect(routeUtterance("hey sherpa, why does the next step work?", idle).kind).toBe("ask");
    expect(routeUtterance("hey sherpa, how do I stop the server?", idle).kind).toBe("ask");
  });
});

describe("what is read aloud", () => {
  it("speaks formulas as words", () => {
    expect(speakable("5^2 + 12^2 = 13^2")).toBe("5 squared plus 12 squared equals 13 squared");
    expect(speakable("x^2 = 5^2 + 12^2 = 169, so x = 13")).toBe("x squared equals 5 squared plus 12 squared equals 169, so x equals 13");
    expect(speakable("2^3 and 2^{10}")).toBe("2 cubed and 2 to the power 10");
    expect(speakable("sqrt(169) = 13")).toBe("the square root of (169) equals 13");
  });

  it("drops markup and says symbols in words", () => {
    expect(speakable("Click 'Access & Identity' in the *left* menu")).toBe("Click 'Access and Identity' in the left menu");
    expect(speakable("Use `Add service`")).toBe("Use Add service");
  });
});

// ---- audio ------------------------------------------------------------------------------

const FRAME = 480; // 30 ms at 16 kHz
function tone(ms: number, amplitude: number, hz = 220): Int16Array {
  const n = Math.round((ms / 1000) * SAMPLE_RATE);
  const out = new Int16Array(n);
  for (let i = 0; i < n; i++) out[i] = Math.round(amplitude * 32767 * Math.sin((2 * Math.PI * hz * i) / SAMPLE_RATE));
  return out;
}
function hiss(ms: number, amplitude: number): Int16Array {
  const n = Math.round((ms / 1000) * SAMPLE_RATE);
  const out = new Int16Array(n);
  let seed = 12345;
  for (let i = 0; i < n; i++) {
    seed = (seed * 1103515245 + 12345) & 0x7fffffff;
    out[i] = Math.round(((seed / 0x7fffffff) * 2 - 1) * amplitude * 32767);
  }
  return out;
}
function concat(...parts: Int16Array[]): Int16Array {
  const out = new Int16Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}
function feed(segmenter: Segmenter, signal: Int16Array) {
  const events = [];
  for (let i = 0; i + FRAME <= signal.length; i += FRAME) events.push(...segmenter.push(signal.subarray(i, i + FRAME)));
  return events;
}

describe("packing audio", () => {
  it("writes a WAV header whisper can read", () => {
    const wav = pcmToWav(Int16Array.from([1, -1, 300]));
    const view = new DataView(wav.buffer);

    expect(String.fromCharCode(...wav.slice(0, 4))).toBe("RIFF");
    expect(String.fromCharCode(...wav.slice(8, 16))).toBe("WAVEfmt ");
    expect(view.getUint16(20, true)).toBe(1); // PCM
    expect(view.getUint16(22, true)).toBe(1); // mono
    expect(view.getUint32(24, true)).toBe(16000);
    expect(view.getUint16(34, true)).toBe(16);
    expect(view.getUint32(40, true)).toBe(6);
    expect(view.getInt16(48, true)).toBe(300);
    expect(wav.length).toBe(44 + 6);
  });

  it("measures loudness", () => {
    expect(rms(new Int16Array(100))).toBe(0);
    expect(rms(tone(100, 0.5))).toBeCloseTo(0.5 / Math.SQRT2, 1);
  });
});

describe("cutting speech out of a stream", () => {
  it("finds one utterance between two silences, with its start and end kept", () => {
    const s = new Segmenter();
    const events = feed(s, concat(hiss(1000, 0.004), tone(1200, 0.2), hiss(1500, 0.004)));

    expect(events.map((e) => e.type)).toEqual(["start", "utterance"]);
    const utterance = events[1] as { type: "utterance"; pcm: Int16Array; speechMs: number };
    expect(utterance.speechMs).toBeGreaterThan(1000);
    expect(utterance.pcm.length / SAMPLE_RATE).toBeGreaterThan(1.2); // the speech and a little around it
    expect(utterance.pcm.length / SAMPLE_RATE).toBeLessThan(2.2);
  });

  it("does not end an utterance at a short pause between words", () => {
    const s = new Segmenter();
    const events = feed(s, concat(hiss(500, 0.004), tone(600, 0.2), hiss(300, 0.004), tone(600, 0.2), hiss(1500, 0.004)));

    expect(events.filter((e) => e.type === "utterance")).toHaveLength(1);
  });

  it("splits two requests separated by a long silence", () => {
    const s = new Segmenter();
    const events = feed(s, concat(hiss(500, 0.004), tone(800, 0.2), hiss(1500, 0.004), tone(800, 0.2), hiss(1500, 0.004)));

    expect(events.filter((e) => e.type === "utterance")).toHaveLength(2);
  });

  it("drops a click as too short", () => {
    const s = new Segmenter();
    const events = feed(s, concat(hiss(800, 0.004), tone(150, 0.3), hiss(1500, 0.004)));

    expect(events.some((e) => e.type === "utterance")).toBe(false);
  });

  it("is not triggered by the quiet hum of a room", () => {
    const s = new Segmenter();

    expect(feed(s, hiss(6000, 0.004))).toEqual([]);
  });

  it("learns the room: noise that is a little louder is not speech either, speech still is", () => {
    const s = new Segmenter();
    const events = feed(s, concat(hiss(3000, 0.015), tone(900, 0.25), hiss(1500, 0.015)));

    expect(events.filter((e) => e.type === "utterance")).toHaveLength(1);
  });

  it("cuts speech that never stops (a lecture video) instead of waiting for ever", () => {
    const s = new Segmenter();
    const events = feed(s, concat(hiss(500, 0.004), tone(20000, 0.2)));

    expect(events.some((e) => e.type === "dropped" && e.reason === "too long")).toBe(true);
    expect(events.some((e) => e.type === "utterance")).toBe(false);
  });
});

describe("Piper speech helpers", () => {
  it("reads the samples and the sample rate of a WAV file", async () => {
    const { parseWav } = await import("../src/voice/audio");
    const pcm = Int16Array.from([0, 1000, -1000, 32767]);
    const wav = pcmToWav(pcm, 22050);
    const parsed = parseWav(wav);
    expect(parsed.sampleRate).toBe(22050);
    expect(Array.from(parsed.pcm)).toEqual(Array.from(pcm));
    expect(() => parseWav(new Uint8Array(20))).toThrow();
  });

  it("splits text into sentences and joins very short pieces", async () => {
    const { splitSentences } = await import("../src/voice/speakable");
    expect(splitSentences("First, look at the triangle. Then, the square on side a! Done?")).toEqual([
      "First, look at the triangle.",
      "Then, the square on side a!",
      "Done?",
    ]);
    expect(splitSentences("So. The hypotenuse is the longest side.")).toEqual(["So. The hypotenuse is the longest side."]);
    expect(splitSentences("no punctuation here")).toEqual(["no punctuation here"]);
    expect(splitSentences("  ")).toEqual([]);
  });
});

describe("narration", () => {
  it("says superscript powers in words", () => {
    expect(speakable("x\u00b2 = 6\u00b2 + 8\u00b2")).toBe("x squared equals 6 squared plus 8 squared");
  });

  it("uses the rewritten words only when the backend really rewrote them", async () => {
    const { narrate } = await import("../src/backendClient");
    const reply = (body: unknown, ok = true) => (async () => ({ ok, json: async () => body }) as Response) as unknown as typeof fetch;
    const real = globalThis.fetch;
    try {
      globalThis.fetch = reply({ spoken: "Said nicely.", source: "nemotron" });
      expect(await narrate("http://x", "t", { caption: "c", question: "", earlier: [] })).toBe("Said nicely.");
      globalThis.fetch = reply({ spoken: "c", source: "caption" });
      expect(await narrate("http://x", "t", { caption: "c", question: "", earlier: [] })).toBeUndefined();
      globalThis.fetch = reply({}, false); // an older backend answers 404
      expect(await narrate("http://x", "t", { caption: "c", question: "", earlier: [] })).toBeUndefined();
      globalThis.fetch = (async () => {
        throw new Error("offline");
      }) as unknown as typeof fetch;
      expect(await narrate("http://x", "t", { caption: "c", question: "", earlier: [] })).toBeUndefined();
    } finally {
      globalThis.fetch = real;
    }
  });
});
