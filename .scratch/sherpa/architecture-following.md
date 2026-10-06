# How the app follows a task when the page changes

The problem: the tutor points at something on a page. The learner clicks, the page changes. The marks drawn for the old page are now wrong, and the learner should not have to type "done" after every click.

The app cannot read other programs' pages (unlike a browser extension), so it works from pixels. There are four parts: eyes, a reflex, a brain and guards.

```
                       +-----------------+
 screen ---video--->   |  watcher window |  (hidden, reads the screen at 15 pictures a second)
 (our own windows      |  ChangeDetector |
  are not in it)       +--------+--------+
                                |  "stale"  "fire"
                                v
                      +---------+----------+
                      |   main process     |  state: goal, following, canvas, conversation
                      +----+----------+----+
                  reflex   |          |   brain
            markStale()    |          |   fireAuto() -> ask(trigger "screen_changed")
                           v          v
                   overlay fades   backend turn: new screenshot + goal + history
                   the pointing    -> model judges: continue / off_track / waiting / done
                   marks (0.12 s)  -> next step drawn, written in the chat, spoken
```

## 1. Eyes: the watcher (desktop/src/follow/watcher.ts, changeDetector.ts)

- A hidden window opens the screen as a video stream (getUserMedia with the desktop source). Windows of the app itself (overlay, chat, voice orb) are excluded from captures, so the tutor never sees its own marks.
- Each picture is turned to grayscale and averaged down 4 by 4 (640 x 360 becomes 160 x 90). Averaging makes the flicker the capture produces on single pixels disappear; real changes survive.
- The detector compares every picture with the **baseline**: the screen as it was when the marks were drawn. It also compares with the previous picture, to know whether things are still moving.
- Cells that keep changing (a playing video, a spinner) are left out until they are still, the area around the mouse pointer is left out (its position comes from the main process), and so is the taskbar (its clock changes every minute).
- The picture is divided into blocks. A real change is cells piling up in a block (a few typed letters, a dialog, a new page); sparse noise spread over the screen is not. Motion is only counted in blocks that carry the change, or touch one, so flicker elsewhere cannot keep it "moving".

## 2. Reflex: marks go at once

- If more than 4 percent of the screen differs from the baseline, the detector says **stale** on that very picture (about 0.1 s after the page changed).
- main.ts removes the pointing marks (box, ellipse, arrow, highlight, label, step number) from its canvas and tells the overlay, which fades them in 0.12 s. Formulas, squares and diagrams stay. Automatic playback of an old answer stops.
- This does not wait for the model: it is a reflex.

## 3. Brain: the next step by itself

- When the change has **settled** (0.7 s of stillness after a page change, 1 s after a small change such as typing) the detector says **fire**.
- main.ts sends a normal turn with `trigger: "screen_changed"`: a fresh full capture, the goal, the conversation and the previous regions. No message from the learner is shown; the chat gets a quiet line.
- The prompt tells the model what to judge: `progress` is `continue` (on track: give the next step), `off_track` (say where the learner ended up and how to get back), `waiting` (they are still typing or the page is loading: no steps, nothing said) or `done` (the goal is reached).
- The backend keeps nothing between turns. The desktop app keeps the goal (the tutor states it on the first answer and repeats it), the conversation, the canvas and the regions.
- If the learner acted while an answer was still being written, the baseline is the screen the answer was started on (the watcher kept a copy at that moment), so the change is noticed straight away.

## 4. Guards

- Following can be paused (switch in the chat, "pause" by voice) and the task can be ended (End task, Ctrl+Shift+S, "stop" by voice). Stop also pauses following so it does not start again by itself.
- At most 25 automatic turns per goal; three `off_track` answers in a row pause following; 15 minutes without activity pause it; a new chat forgets the task.
- An automatic turn never starts while another answer is being fetched.
- A watcher that does not come up within 5 seconds is started once more.

## Compared with Pointr

Pointr is a Chrome extension. It listens to clicks, polls the URL, checks that the target element is still attached and visible, and waits for the DOM to settle; it replaces the overlay for each step, loops automatically (cap 40 turns), and keeps goal and history per tab. We do the same jobs from pixels, which works in any application (a desktop app, a video, a remote desktop) but cannot know that a click happened, only what the screen looked like afterwards.

## Known limits

- Scrolling counts as a page change (marks go, the next step comes from the model), which is right for pointing but not free.
- A page that animates everywhere all the time may never settle; the volatile-cell mask copes with a video or a spinner, not with the whole page moving.
- A change confined to the taskbar, or hidden under the mouse pointer, is not seen.
- Each automatic turn is a model call (about 3 seconds); typing usually produces `waiting`, which costs a call and says nothing.
