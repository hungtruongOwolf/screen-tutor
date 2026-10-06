// What a transcribed utterance means: is it for the tutor at all, is it a command ("open chat",
// "stop") or a request to answer. Pure, so it is tested without a microphone.
//
// The microphone hears everything in the room, including a lecture playing on the screen, so the
// tutor only reacts when it is addressed:
//   - the utterance starts with the wake word ("hey Sherpa ...", "Sherpa, ..."), or
//   - it is part of a conversation that is going on (the tutor has just spoken or been spoken to), or
//   - a task is being followed and it is one of the short things said while doing a task
//     ("done", "next", "I don't see it", "stop").

export type Command =
  | "open-chat"
  | "close-chat"
  | "stop"
  | "new-chat"
  | "pause-following"
  | "resume-following"
  | "next-step"
  | "previous-step"
  | "clear-marks"
  | "mute"
  | "repeat"
  | "quiet" // stop speaking and stay quiet
  | "speak"; // speak the answers again

export type Intent =
  | { kind: "ignore"; reason: string }
  | { kind: "wake" } // only the wake word: it is listening
  | { kind: "command"; command: Command }
  | { kind: "ask"; text: string };

export interface Context {
  inConversation: boolean; // the tutor spoke, or was spoken to, a moment ago
  taskActive: boolean; // a task is being followed
}

// A wake word is often heard as something close to it ("Tudor", "teacher"), and people open with one or
// two greetings ("Hello, hey tutor ...").
const GREETING = /^(?:(?:hey|hay|hi|hello|ok|okay|yo|so|well|um|uh)[\s,.!-]+)+/i;

// The words that call the assistant (the first one is how it is named in hints). "Sherpa" has two
// syllables and is easy to say; "Nova" works too.
export const DEFAULT_WAKE_WORDS = ["sherpa", "nova"];
let wakeWords = [...DEFAULT_WAKE_WORDS];

export function configureWake(words: string[]): void {
  const clean = words.map((w) => w.trim().toLowerCase().replace(/[^a-z']/g, "")).filter(Boolean);
  wakeWords = clean.length > 0 ? clean : [...DEFAULT_WAKE_WORDS];
}

export function wakeLabel(): string {
  const first = wakeWords[0] ?? "sherpa";
  return first.charAt(0).toUpperCase() + first.slice(1);
}

// What recognisers write when they mishear one of the wake words.
const ALIASES: Record<string, string[]> = {
  tutor: ["teacher", "teachers", "tutoring", "tudo", "tutoria", "tooter", "tudder", "tutter"],
  sherpa: ["sherper", "shirpa", "shurpa", "sharper", "sherpas", "sherpa's", "surpa", "sherba", "sherpah", "shepa", "sherpar"],
  nova: ["noah", "novah", "nuva", "nover", "novo", "novas", "nova's"],
};

function editDistance(a: string, b: string): number {
  const row = Array.from({ length: b.length + 1 }, (_, i) => i);
  for (let i = 1; i <= a.length; i++) {
    let previous = row[0] as number;
    row[0] = i;
    for (let j = 1; j <= b.length; j++) {
      const kept = row[j] as number;
      row[j] = Math.min(kept + 1, (row[j - 1] as number) + 1, previous + (a[i - 1] === b[j - 1] ? 0 : 1));
      previous = kept;
    }
  }
  return row[b.length] as number;
}

// Short words must match exactly or nearly (a near miss on a short word is another word), longer ones
// may be a letter or two off.
function isWakeWord(word: string): boolean {
  const w = word.toLowerCase();
  return wakeWords.some((wake) => {
    if (w === wake || (ALIASES[wake] ?? []).includes(w)) return true;
    const allowed = wake.length >= 5 ? 2 : wake.length === 4 ? 1 : 0;
    return allowed > 0 && editDistance(w, wake) <= allowed;
  });
}

// The text after the wake word (possibly empty), or undefined when it does not start with one.
function afterWake(text: string): string | undefined {
  const greeting = GREETING.exec(text);
  const rest = greeting ? text.slice(greeting[0].length) : text;
  const one = /^([A-Za-z']+)[\s,.:;!?-]*/.exec(rest);
  if (one && isWakeWord(one[1] as string)) return rest.slice(one[0].length).trim();
  // "no va" heard for "nova"
  const two = /^([A-Za-z']+)[\s,.-]+([A-Za-z']+)[\s,.:;!?-]*/.exec(rest);
  if (two && isWakeWord((two[1] as string) + (two[2] as string))) return rest.slice(two[0].length).trim();
  return undefined;
}

// Things recognisers write for silence and background noise.
const NOISE = new Set([
  "", "you", "thank you", "thanks", "thanks for watching", "thank you for watching", "bye", "bye bye",
  "okay", "ok", "uh", "um", "hmm", "mm", "ah", "oh", "so", "yeah", "the", "and",
]);

function clean(text: string): string {
  return text
    .replace(/\[[^\]]*\]|\([^)]*\)|\*[^*]*\*/g, " ") // [BLANK_AUDIO], (music), *sound*
    .replace(/[^\p{L}\p{N}'\s,.:;!?-]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function words(text: string): string {
  return text
    .toLowerCase()
    .replace(/[^\p{L}\p{N}'\s]/gu, " ")
    .replace(/\s+/g, " ")
    .trim();
}

const COMMANDS: [RegExp, Command][] = [
  [/^(?:please )?(?:open|show|bring up|pull up)(?: me)?(?: the)? (?:chat|chat window|chat panel|text chat|typing)(?: please)?$/, "open-chat"],
  [/^(?:let me|i want to|i will|i'll|can i|i need to) type(?: something)?(?: please)?$/, "open-chat"],
  [/^(?:please )?(?:type|typing mode|text mode)$/, "open-chat"],
  [/^(?:please )?(?:hide|close|dismiss|put away)(?: the)? (?:chat|chat window|chat panel)(?: please)?$/, "close-chat"],
  [/^(?:stop|cancel|abort|end|finish)(?: it| this| that| now| everything)?(?: the)?(?: task)?(?: please)?$/, "stop"],
  [/^(?:that'?s|that is) (?:enough|all)$/, "stop"],
  [/^(?:never ?mind|forget it)$/, "stop"],
  [/^(?:start|begin)(?: a)? (?:new chat|new conversation|over|again|fresh)$/, "new-chat"],
  [/^(?:new chat|new conversation|reset|start over|clear (?:the )?(?:chat|conversation))$/, "new-chat"],
  [/^(?:pause|hold on|wait)(?: following| for me| a (?:sec|second|moment|minute))?$/, "pause-following"],
  [/^(?:resume|continue|keep going|carry on|go on)(?: following)?$/, "resume-following"],
  [/^(?:next|next step|go to the next step|show (?:me )?the next (?:step|one))$/, "next-step"],
  [/^(?:previous|previous step|back|go back|last step|the (?:previous|last) step)$/, "previous-step"],
  [/^(?:clear|remove|hide|erase)(?: all| the| all the)?(?: marks| drawings| drawing| markings| boxes| screen| overlay)$/, "clear-marks"],
  [/^(?:mute|stop listening|go to sleep|mute (?:the )?(?:mic|microphone))$/, "mute"],
  [/^(?:repeat|say (?:that )?again|repeat that|what did you say|come again|say it again)$/, "repeat"],
  [/^(?:be quiet|quiet|stop talking|shut up|silence|hush|stop speaking)$/, "quiet"],
  [/^(?:speak|talk to me|read it (?:out|aloud)|read (?:it )?to me|start talking|speak again)$/, "speak"],
];

// What people say while following a task, without addressing the tutor.
const TASK_TALK: RegExp[] = [
  /^(?:ok(?:ay)?,? )?(?:i )?(?:did it|done|i'?m done|finished|i clicked(?: it)?|clicked(?: it)?|i'?ve done (?:that|it)|that'?s done|it'?s done)\b/,
  /^(?:ok(?:ay)?,? )?(?:what(?:'s| is)? next|what now|next(?: step)?|then what|and now)\b/,
  /^(?:i )?(?:don'?t|can'?t|do not|cannot) (?:see|find) (?:it|that|the|a|any)\b/,
  /^(?:where is (?:it|that)|where do i click|where is the)\b/,
  /^(?:i'?m )?(?:lost|stuck|confused)\b/,
  /^(?:wait|hold on|stop|pause|cancel)\b/,
];

export function routeUtterance(raw: string, context: Context): Intent {
  const text = clean(raw);
  const plain = words(text);
  if (NOISE.has(plain)) return { kind: "ignore", reason: "noise" };

  const afterWord = afterWake(text);
  let rest = text;
  let addressed = false;
  if (afterWord !== undefined) {
    rest = afterWord;
    addressed = true;
    if (!rest) return { kind: "wake" };
  }
  const spoken = words(rest);

  const command = COMMANDS.find(([pattern]) => pattern.test(spoken));
  if (command) {
    // Opening or closing the chat is a phrase nobody says by accident; "stop" and "next" are only
    // taken from the room when something is going on.
    const alwaysOk: Command[] = ["open-chat", "close-chat"];
    const whenBusy: Command[] = ["stop", "next-step", "previous-step", "pause-following", "resume-following", "repeat", "mute", "quiet"];
    const name = command[1];
    if (addressed || context.inConversation || alwaysOk.includes(name) || (context.taskActive && whenBusy.includes(name))) {
      return { kind: "command", command: name };
    }
    return { kind: "ignore", reason: "not addressed" };
  }

  if (addressed || context.inConversation) {
    if (words(rest).length < 2 && NOISE.has(spoken)) return { kind: "ignore", reason: "noise" };
    return { kind: "ask", text: rest };
  }
  if (context.taskActive && TASK_TALK.some((pattern) => pattern.test(spoken))) {
    return { kind: "ask", text: rest };
  }
  return { kind: "ignore", reason: "not addressed" };
}
