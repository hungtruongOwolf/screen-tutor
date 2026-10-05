# 24: Guide a newcomer through a complicated page

**What to build:** a second use case next to teaching: someone new to a cloud console (or any busy settings page) says what they want to do and is led click by click, with the chat remembering where they are.

**Blocked by:** 22, 23.

**Status:** built and tried on a made-up three-screen console and on two real public pages; owner check pending.

- [x] Prompt rules for guiding: one action per step, the control named as written, a box or arrow on its own region, only what is visible, nothing drawn for a screen that is not open yet (say what will appear and ask them to say "done"), numbered marks for the fields of a form, never ask for passwords or keys in the chat, warn before something irreversible.
- [x] A mock console ("Acme Cloud": dashboard, users, create user) in `backend/tools/mock_console/console.html` and three sample screenshots, with a guided session run against the live model: it found Access & Identity, then the user, then walked the form field by field and warned that the key is shown only once.
- [x] The web playground has a "Guide me through a cloud console" sample with an "I clicked it: show the next screen" button that plays the same session without installing anything.
- [x] Region proposer: lines of text are regions of their own (menu items, list rows are pointable); the cap is 70 regions.
- [ ] Try on real consoles (the owner's AWS, Nebius, Tavily and Devpost pages, or the public AWS and Google Cloud pricing calculators) and note what goes wrong; icon-only buttons and canvas-drawn widgets have no text to point at.
- [ ] Possible follow-up: watch the screen after a step and continue by itself when it changes ("follow my clicks").
