import { beforeEach, describe, expect, it, vi } from "vitest";
import { ChatView, type PanelCommands } from "../src/panel/chatView";

function setup() {
  document.body.innerHTML = '<div id="root"></div>';
  const commands: PanelCommands = {
    send: vi.fn(), newChat: vi.fn(), clearDrawings: vi.fn(), hide: vi.fn(), stop: vi.fn(),
    goTo: vi.fn(), step: vi.fn(), togglePlay: vi.fn(), typed: vi.fn(), toggleFollow: vi.fn(), endTask: vi.fn(),
  };
  const view = new ChatView(document.getElementById("root") as HTMLElement, commands);
  const $ = (selector: string) => document.querySelector(selector) as HTMLElement;
  return { view, commands, $ };
}

describe("the task bar of the chat", () => {
  let t: ReturnType<typeof setup>;
  beforeEach(() => {
    t = setup();
  });

  it("is hidden until there is a goal", () => {
    expect(t.$(".task").hidden).toBe(true);

    t.view.handle({ type: "task", goal: "Create an access key", following: true });

    expect(t.$(".task").hidden).toBe(false);
    expect(t.$(".goal").textContent).toBe("Create an access key");
    expect(t.$(".follow").textContent).toBe("Following your clicks");
  });

  it("shows paused when following is off, and the switch asks to toggle it", () => {
    t.view.handle({ type: "task", goal: "g", following: false });

    expect(t.$(".follow").textContent).toBe("Paused");
    expect(t.$(".follow").classList.contains("on")).toBe(false);
    t.$(".follow").click();
    expect(t.commands.toggleFollow).toHaveBeenCalledTimes(1);
  });

  it("has an End task button that asks to end the task", () => {
    t.view.handle({ type: "task", goal: "g", following: true });

    t.$(".end").click();

    expect(t.commands.endTask).toHaveBeenCalledTimes(1);
  });

  it("goes away when the goal is cleared or the chat is reset", () => {
    t.view.handle({ type: "task", goal: "g", following: true });
    t.view.handle({ type: "task", goal: null, following: true });
    expect(t.$(".task").hidden).toBe(true);

    t.view.handle({ type: "task", goal: "g", following: true });
    t.view.handle({ type: "reset" });
    expect(t.$(".task").hidden).toBe(true);
  });

  it("writes a quiet line for what the app did by itself and puts the next steps in a new card", () => {
    t.view.handle({ type: "user", text: "help" });
    t.view.handle({ type: "step", index: 0, total: 1, streaming: false, caption: "First", animate: false, seq: 1 });
    t.view.handle({ type: "auto", text: "The screen changed" });
    t.view.handle({ type: "step", index: 0, total: 1, streaming: false, caption: "Second", animate: false, seq: 2 });

    expect(document.querySelectorAll(".card")).toHaveLength(2);
    expect(t.$(".note").textContent).toBe("The screen changed");
    expect(document.querySelectorAll(".bubble.user")).toHaveLength(1);
  });
});
