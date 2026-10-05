import { describe, expect, it } from "vitest";
import { Conversation } from "../src/chat/conversation";

describe("the conversation", () => {
  it("starts empty and remembers who said what, in order", () => {
    const chat = new Conversation();
    expect(chat.history()).toEqual([]);

    chat.addUser("How do I price a server?");
    chat.addAssistant(["Click Add service.", "Then search for EC2."]);

    expect(chat.history()).toEqual([
      { role: "user", text: "How do I price a server?" },
      { role: "assistant", text: "Click Add service. Then search for EC2." },
    ]);
  });

  it("ignores empty messages", () => {
    const chat = new Conversation();

    chat.addUser("   ");
    chat.addAssistant([]);
    chat.addAssistant(["", ""]);

    expect(chat.length).toBe(0);
  });

  it("starts again on a new chat", () => {
    const chat = new Conversation();
    chat.addUser("hello");

    chat.reset();

    expect(chat.history()).toEqual([]);
  });

  it("keeps only the latest messages of a very long chat, each trimmed", () => {
    const chat = new Conversation();
    for (let i = 0; i < 40; i++) chat.addUser(`message ${i} ` + "x".repeat(3000));

    const history = chat.history();

    expect(history).toHaveLength(24);
    expect(history[history.length - 1]?.text.startsWith("message 39")).toBe(true);
    expect(history.every((m) => m.text.length <= 1200)).toBe(true);
  });

  it("hands out copies, so the caller cannot change the memory", () => {
    const chat = new Conversation();
    chat.addUser("hi");

    chat.history()[0]!.text = "changed";

    expect(chat.history()[0]?.text).toBe("hi");
  });
});
