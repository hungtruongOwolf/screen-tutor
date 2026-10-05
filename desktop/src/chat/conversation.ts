// The conversation with the tutor: what the learner asked and what the tutor said,
// kept so each new question can be sent together with the thread (the backend keeps
// nothing between turns). Pure, so it can be tested without Electron.

export interface ChatMessage {
  role: "user" | "assistant";
  text: string;
}

// The backend trims further; this only keeps the memory of a long chat bounded.
const KEEP = 24;
const MAX_CHARS = 1200;

export class Conversation {
  private messages: ChatMessage[] = [];

  addUser(text: string): void {
    this.add("user", text);
  }

  // What the tutor said: the captions of its steps, joined.
  addAssistant(captions: string[]): void {
    this.add("assistant", captions.filter(Boolean).join(" "));
  }

  // The messages before the one being asked now (call before addUser).
  history(): ChatMessage[] {
    return this.messages.map((m) => ({ ...m }));
  }

  get length(): number {
    return this.messages.length;
  }

  reset(): void {
    this.messages = [];
  }

  private add(role: ChatMessage["role"], text: string): void {
    const clean = text.replace(/\s+/g, " ").trim();
    if (!clean) return;
    this.messages.push({ role, text: clean.length > MAX_CHARS ? clean.slice(0, MAX_CHARS - 1) + "…" : clean });
    if (this.messages.length > KEEP) this.messages.splice(0, this.messages.length - KEEP);
  }
}
