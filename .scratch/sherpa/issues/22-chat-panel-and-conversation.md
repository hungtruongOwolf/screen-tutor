# 22: A real chat: panel, memory, new chat

**What to build:** the owner found that every question needed Ctrl+Shift+E again, nothing remembered the conversation, and there was no clear way to start fresh. Now a chat panel stays open in the corner; each message captures the screen and goes to the backend with the conversation.

**Blocked by:** 20.

**Status:** built; owner check on screen pending.

- [x] A chat panel window (hidden from captures, always on top, draggable by its bar): messages, the tutor's steps as a transcript, status line, quick replies, step controls (previous, pause or resume, next), a message box (Enter sends, Shift+Enter new line, Esc hides).
- [x] Ctrl+Shift+E shows and hides the panel; Ctrl+Shift+N and the New chat button start fresh (conversation, drawings, steps); Ctrl+Shift+X and the Clear button take the drawings off but keep the chat. Stop cancels the request in flight.
- [x] The backend takes the conversation (`history`, last 10 messages used, each trimmed) and the model is told how to use it ("done", "next", "why?" refer to it; the screen may have changed). The answer carries up to three `follow_ups` shown as quick replies.
- [x] Words moved from the overlay into the chat (no more caption bar over the screen); a step is typed into the chat while its drawing is drawn; clicking a step in the chat plays it again.
- [x] Pause and resume of automatic playback (StepPlayer.resume, playing state) and the sources and quick replies shown after the last step has played.
- [x] The web playground uses the same chat view (one source file, one stylesheet), with samples that start by themselves and a multi-screen sample that simulates the learner's clicks.
- [x] Checked in real Electron with hidden windows (preload bridge, events in, commands out, rendering) and in Chrome against the live backend.
