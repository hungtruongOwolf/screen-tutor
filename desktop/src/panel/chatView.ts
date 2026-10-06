// The chat panel's view: builds its own DOM inside `root` and reacts to the events
// the main process sends. It holds no business logic: what the learner does goes out
// through `api`, what the tutor does comes in through `handle`.

import type { PanelEvent } from "../contract";

export interface PanelCommands {
  send(text: string): void;
  newChat(): void;
  clearDrawings(): void;
  hide(): void;
  stop(): void;
  goTo(index: number): void;
  step(direction: "prev" | "next"): void;
  togglePlay(): void;
  typed(seq: number): void;
  toggleFollow(): void;
  endTask(): void;
}

const WELCOME_CHIPS = [
  "Explain what is on my screen",
  "I am lost. What should I click?",
  "Teach me this step by step",
];
const FALLBACK_CHIPS = ["Explain more simply", "Why?"];

const TYPING_MS = 1800; // a caption is typed in over at most this long

function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  className?: string,
  text?: string,
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

export class ChatView {
  private readonly thread = el("div", "thread");
  private readonly task = el("div", "task");
  private readonly goalText = el("span", "goal");
  private readonly followButton = el("button", "follow");
  private readonly endButton = el("button", "end", "End task");
  private readonly status = el("div", "status");
  private readonly chips = el("div", "chips");
  private readonly controls = el("div", "controls");
  private readonly stepLabel = el("span", "step-label");
  private readonly playButton = el("button", "icon", "⏸");
  private readonly input = el("textarea", "input");
  private readonly sendButton = el("button", "send", "Send");

  private busy = false;
  private card: HTMLElement | undefined; // the tutor's answer being shown
  private rows: HTMLElement[] = [];
  private typing: { timer: ReturnType<typeof setInterval>; finish: () => void } | undefined;

  constructor(
    root: HTMLElement,
    private readonly commands: PanelCommands,
  ) {
    root.replaceChildren(this.build());
    this.showWelcome();
  }

  // ---- building the page ----------------------------------------------------------

  private build(): HTMLElement {
    const app = el("div", "app");

    const bar = el("div", "bar");
    const brand = el("div", "brand");
    brand.append(el("span", "dot"), document.createTextNode("Sherpa"));
    const actions = el("div", "actions");
    actions.append(
      this.action("New chat", "New chat (Ctrl+Shift+N): forgets this conversation and the drawings", () => this.commands.newChat()),
      this.action("Clear", "Clear the drawings on the screen (Ctrl+Shift+X); the chat stays", () => this.commands.clearDrawings()),
      this.action("×", "Hide (Esc). Ctrl+Shift+E brings it back", () => this.commands.hide(), "close"),
    );
    bar.append(brand, actions);

    const prev = el("button", "icon", "◀");
    prev.title = "Previous step (Ctrl+Shift+,)";
    prev.addEventListener("click", () => this.commands.step("prev"));
    const next = el("button", "icon", "▶");
    next.title = "Next step (Ctrl+Shift+.)";
    next.addEventListener("click", () => this.commands.step("next"));
    this.playButton.title = "Pause or resume the automatic steps";
    this.playButton.addEventListener("click", () => this.commands.togglePlay());
    this.controls.append(prev, this.playButton, next, this.stepLabel);
    this.controls.hidden = true;

    const composer = el("form", "composer");
    this.input.rows = 1;
    this.input.placeholder = "Ask about your screen…";
    this.input.setAttribute("aria-label", "Message");
    this.input.addEventListener("input", () => this.grow());
    this.input.addEventListener("keydown", (event) => {
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        this.submit();
      } else if (event.key === "Escape") {
        this.commands.hide();
      }
    });
    this.sendButton.type = "submit";
    composer.addEventListener("submit", (event) => {
      event.preventDefault();
      if (this.busy) this.commands.stop();
      else this.submit();
    });
    composer.append(this.input, this.sendButton);

    this.followButton.type = "button";
    this.followButton.addEventListener("click", () => this.commands.toggleFollow());
    this.endButton.type = "button";
    this.endButton.title = "End this task: stop following and take the marks off (Ctrl+Shift+S)";
    this.endButton.addEventListener("click", () => this.commands.endTask());
    this.task.append(this.goalText, this.followButton, this.endButton);
    this.task.hidden = true;

    app.append(bar, this.task, this.thread, this.status, this.chips, this.controls, composer);
    return app;
  }

  private action(label: string, title: string, run: () => void, extra = ""): HTMLButtonElement {
    const button = el("button", `action ${extra}`.trim(), label);
    button.type = "button";
    button.title = title;
    button.addEventListener("click", run);
    return button;
  }

  // ---- what the learner does ------------------------------------------------------

  private submit(): void {
    const text = this.input.value.trim();
    if (!text || this.busy) return;
    this.input.value = "";
    this.grow();
    this.commands.send(text);
  }

  private grow(): void {
    this.input.style.height = "auto";
    this.input.style.height = `${Math.min(this.input.scrollHeight, 110)}px`;
  }

  // ---- what the tutor does --------------------------------------------------------

  handle(event: PanelEvent): void {
    switch (event.type) {
      case "reset":
        this.finishTyping();
        this.thread.replaceChildren();
        this.card = undefined;
        this.rows = [];
        this.controls.hidden = true;
        this.showTask(null, false);
        this.setStatus(null);
        this.setBusy(false);
        this.showWelcome();
        break;
      case "user":
        this.clearWelcome();
        this.chips.replaceChildren();
        this.card = undefined;
        this.rows = [];
        this.controls.hidden = true;
        this.append(el("div", "bubble user", event.text));
        break;
      case "busy":
        this.setBusy(event.value);
        break;
      case "status":
        this.setStatus(event.text);
        break;
      case "step":
        this.showStep(event);
        break;
      case "done":
        this.finishTyping();
        this.addSources(event.sources);
        this.setChips(event.followUps.length > 0 ? event.followUps : FALLBACK_CHIPS);
        this.scroll();
        break;
      case "error":
        this.setStatus(null);
        this.append(el("div", "notice error", event.text));
        break;
      case "playing":
        this.playButton.textContent = event.value ? "⏸" : "▶";
        this.playButton.title = event.value ? "Pause the automatic steps" : "Play the steps on their own";
        break;
      case "focus":
        this.input.focus();
        break;
      case "task":
        this.showTask(event.goal, event.following);
        break;
      case "auto":
        // The app acted by itself: a quiet line, and the next steps go in a new card.
        this.finishTyping();
        this.card = undefined;
        this.rows = [];
        this.controls.hidden = true;
        this.chips.replaceChildren();
        this.append(el("div", "note", event.text));
        break;
    }
  }

  private showTask(goal: string | null, following: boolean): void {
    this.task.hidden = !goal;
    this.goalText.textContent = goal ?? "";
    this.goalText.title = goal ? `Goal: ${goal}` : "";
    this.followButton.textContent = following ? "Following your clicks" : "Paused";
    this.followButton.classList.toggle("on", following);
    this.followButton.title = following
      ? "I watch the screen and give the next step when it changes. Click to pause."
      : "Click to let me follow your clicks again.";
  }

  private showWelcome(): void {
    const welcome = el("div", "welcome");
    welcome.append(
      el("h2", undefined, "Ask about anything on your screen"),
      el("p", undefined, "I look at your screen when you send a message, then explain and draw on it. Keep chatting: I remember the conversation and look at the screen again each time."),
    );
    this.thread.append(welcome);
    this.setChips(WELCOME_CHIPS);
  }

  private clearWelcome(): void {
    this.thread.querySelector(".welcome")?.remove();
  }

  private setChips(texts: string[]): void {
    this.chips.replaceChildren(
      ...texts.map((text) => {
        const chip = el("button", "chip", text);
        chip.type = "button";
        chip.addEventListener("click", () => {
          if (!this.busy) this.commands.send(text);
        });
        return chip;
      }),
    );
  }

  private setBusy(value: boolean): void {
    this.busy = value;
    this.sendButton.textContent = value ? "Stop" : "Send";
    this.sendButton.classList.toggle("stop", value);
    this.input.placeholder = value ? "Thinking… press Stop to cancel" : "Ask about your screen…";
    if (value) this.chips.replaceChildren();
  }

  private setStatus(text: string | null): void {
    this.status.textContent = text ?? "";
    this.status.hidden = !text;
  }

  private ensureCard(): HTMLElement {
    if (!this.card) {
      this.card = el("div", "card");
      this.append(this.card);
    }
    return this.card;
  }

  private showStep(event: Extract<PanelEvent, { type: "step" }>): void {
    this.setStatus(null);
    const card = this.ensureCard();
    while (this.rows.length <= event.index) {
      const index = this.rows.length;
      const row = el("div", "step");
      row.append(el("span", "badge", String(index + 1)), el("span", "text"));
      row.tabIndex = 0;
      row.title = "Show this step again";
      row.addEventListener("click", () => this.commands.goTo(index));
      row.addEventListener("keydown", (e) => {
        if (e.key === "Enter") this.commands.goTo(index);
      });
      this.rows.push(row);
      card.append(row);
    }
    this.rows.forEach((row, i) => row.classList.toggle("active", i === event.index));
    this.stepLabel.textContent = `Step ${event.index + 1} of ${event.total}${event.streaming ? "+" : ""}`;
    this.controls.hidden = false;

    const text = this.rows[event.index]?.querySelector(".text") as HTMLElement;
    this.finishTyping();
    if (event.animate) {
      this.type(text, event.caption, () => this.commands.typed(event.seq));
    } else {
      text.textContent = event.caption;
    }
    this.scroll();
  }

  private addSources(sources: { title: string; url: string }[]): void {
    if (sources.length === 0 || !this.card) return;
    const line = el("div", "sources", "Source: ");
    const hosts = sources.map((s) => {
      try {
        return new URL(s.url).hostname.replace(/^www\./, "");
      } catch {
        return s.title;
      }
    });
    line.append(document.createTextNode([...new Set(hosts)].join(", ")));
    this.card.append(line);
  }

  // ---- typing effect ---------------------------------------------------------------

  private type(target: HTMLElement, text: string, done: () => void): void {
    target.textContent = "";
    if (!text) {
      done();
      return;
    }
    const every = Math.max(8, Math.min(30, TYPING_MS / text.length));
    let shown = 0;
    const finish = () => {
      clearInterval(timer);
      target.textContent = text;
      this.typing = undefined;
      done();
    };
    const timer = setInterval(() => {
      shown += 1;
      target.textContent = text.slice(0, shown);
      if (shown >= text.length) finish();
      this.scroll();
    }, every);
    this.typing = { timer, finish };
  }

  // Completes the caption being typed (the next step arrived, or the learner moved on).
  private finishTyping(): void {
    this.typing?.finish();
  }

  // ---- small helpers ---------------------------------------------------------------

  private append(node: HTMLElement): void {
    this.thread.append(node);
    this.scroll();
  }

  private scroll(): void {
    this.thread.scrollTop = this.thread.scrollHeight;
  }
}
