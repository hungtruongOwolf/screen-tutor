# Using Sherpa

## How it feels

The chat panel opens in the corner (Ctrl+Shift+E shows and hides it). Type a message and press Enter: the screen is captured at that moment, the detected regions flash across it (you see it reading), and as soon as the first step is written a cursor glides to the first spot, the drawing is drawn on stroke by stroke and the step is typed into the chat. Later steps arrive while it draws and play on by themselves; pause, step back and forward from the panel or with Ctrl+Shift+, and Ctrl+Shift+. . Click a step in the chat to see it again.

It is a real conversation: ask the next thing without any hotkey, or use the suggested replies under the answer ("Done, what next?"). New chat (the button, or Ctrl+Shift+N) forgets the conversation and the drawings; Clear (Ctrl+Shift+X) only takes the drawings off. Pointing marks (boxes, arrows) go away by themselves when the next step draws something; squares and formulas build up.

It can also follow a task by itself: when you are doing something over several pages ("create an access key"), Sherpa states the goal, the chat shows it with a Following switch, and the app watches the screen. When a click changes the page the old marks fade away at once; once the new page has settled Sherpa gives the next step with no message from you, says plainly if you went the wrong way, and says when you are done. Ways to stop: the **Following** switch pauses the automatic steps (the goal stays), **End task** or Ctrl+Shift+S ends the task, the Stop button cancels an answer being fetched (and pauses following so it does not start again by itself), New chat forgets everything, and following pauses by itself after 15 minutes without any activity. Moving the mouse is ignored (a box around the pointer is left out of the comparison).

**Voice.** The first time the app starts it downloads a small speech recogniser and a voice (about 200 MB, to `%LOCALAPPDATA%\sherpa`; both run on your computer, no audio leaves it); from a terminal the same download is `npm run setup:voice` in `desktop/`. Then the app is voice first: a small orb at the bottom left listens. The wake word is **Sherpa**; change it with `WAKE_WORD=...` in `.env` (comma separated, the first one names it in the hints, for example `WAKE_WORD=sherpa,jarvis`). Say "Hey Sherpa, ..." and ask; the answer is drawn on the screen and read aloud step by step. While it is working on a task you can say "done", "what is next", "I don't see it" or "stop" without the wake word, and for 12 seconds after it speaks you can just answer it. To type, say "open chat" (the chat is hidden by default); "close chat" puts it away. Other phrases: "new chat", "pause", "resume", "next step", "go back", "clear the marks", "say that again", "be quiet", "talk to me", "mute". The same script also downloads the voice that talks (Piper, a neural voice that runs on your computer; default `en_US-lessac-medium`; another one with `PIPER_VOICE=en_US-ryan-high` in `.env`, downloaded at the next start) and it speaks 1.2 times faster than normal (`SPEECH_RATE=1.2` in `.env`; 1 is normal). Without it the Windows voices are used. English only. Without the recogniser installed the app works as before, with the chat. If the orb says it cannot hear you: it explains why (usually Windows' Settings, Privacy & security, Microphone, "Let desktop apps access your microphone"), looks for another microphone by itself, and a click on the orb tries again; what it heard is shown on the orb, so a missing wake word is easy to see.

Two ways it helps: **teaching** (explain why something is true, with a proof you can watch) and **guiding** (find where to click in an unfamiliar app or cloud console, one action per step, only pointing at what is on screen). The web playground at `/` (served by the backend) offers both with samples and no install.

## Keys

| Keys | Action |
|---|---|
| Ctrl+Shift+E | Show or hide the chat panel (it keeps the conversation) |
| Ctrl+Shift+N | New chat: forget the conversation and the drawings |
| Ctrl+Shift+M | Mute or unmute the microphone (voice) |
| Ctrl+Shift+Space | Talk now: the next thing you say is for Sherpa, whatever it starts with (voice) |
| Ctrl+Shift+. | Next step of an explanation (Ctrl+> on a US keyboard) |
| Ctrl+Shift+, | Previous step |
| Ctrl+Shift+X | Take the drawings off the screen (the chat stays) |
| Ctrl+Shift+S | Stop: cancel the answer being fetched, end the task being followed (the End task button does the same), take the marks off |
| Ctrl+Shift+R | Recording mode: Sherpa's windows can be seen by a screen recorder (OBS, Game Bar), for a demo video; press again to switch off. `RECORDING=1` starts in it |
| Ctrl+Shift+D | Toggle the debug view: draws every detected region with its number on the last capture |
| Ctrl+Shift+Q | Quit |

## Recording a demo video

The overlay, the chat and the orb are hidden from screen captures on purpose (the AI must never see its own drawings), so a recorder such as OBS or the Windows Game Bar shows a screen without them. Press **Ctrl+Shift+R** (or start with `RECORDING=1`) to switch on recording mode: the windows become visible to recorders. While it is on, the capture sent to the model is taken with Sherpa's windows made invisible for that moment (a short blink at each question, so the model still does not see its own marks), and the screen watcher stops comparing while the overlay draws and measures again from the finished picture, so it does not take the drawing for a page change; the panel and the orb are left out of the comparison. A page change in the first second or so after a drawing starts is not noticed in this mode. Press Ctrl+Shift+R again to go back to normal.
