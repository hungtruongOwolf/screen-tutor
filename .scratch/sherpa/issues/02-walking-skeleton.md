# 02: Walking skeleton: hotkey to drawn shape

**What to build:** A learner presses a global hotkey, the app captures the screen, sends it with a typed placeholder question to a local backend, the backend returns a canned answer containing one shape, and the transparent click-through overlay draws that shape over the screen with a caption. This ticket also sets up the repository structure, the Explain Turn contract (capture, question and current canvas in; explanation, operations, new canvas, chosen regions and trace out), a recorded-response model adapter, and the two test seams (Explain Turn and overlay renderer).

**Blocked by:** None (can start immediately)

**Status:** ready-for-agent

- [x] Hotkey triggers a capture of the primary screen and the app shows it reached the backend (full screen only by design; there is no per-window capture)
- [x] Backend returns a response matching the Explain Turn contract using a fake model adapter
- [ ] Overlay draws the returned shape at the right place and mouse clicks pass through it (needs the manual smoke test in README; code written, app starts and registers hotkeys)
- [x] An Explain Turn test and an overlay renderer test exist and pass (10 backend, 9 renderer)
- [x] README states how to run the app and the tests on Windows
