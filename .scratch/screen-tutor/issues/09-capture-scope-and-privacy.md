# 09: Capture indicator, excluded areas and multi-monitor

**What to build:** The app always captures the full primary screen, and only when the learner triggers it. The learner always sees a clear indicator while a capture is happening and can define screen areas that are never sent (removed on the client before anything leaves the machine). Capture and overlay follow the monitor in use and handle display scaling. There is no per-window capture mode.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] The capture covers the whole screen of the monitor in use
- [ ] A visible indicator shows for the duration of every capture
- [ ] Excluded areas are blacked out in the image before it is sent, verified by a test of what the backend receives
- [ ] Overlay shapes land correctly on a second monitor and at 125% and 150% display scaling
- [ ] Nothing is captured except when triggered
