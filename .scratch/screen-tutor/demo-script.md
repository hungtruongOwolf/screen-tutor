# Demo script (two flows, about 2 minutes each)

Record at 1080p. Backend running (local or the AWS URL), desktop app started with `npm start`. The chat panel sits bottom right. The tutor's windows are hidden from screen captures by default, so a recorder (OBS, Game Bar) would show none of it: press **Ctrl+Shift+R** (recording mode) before recording, and again after. Do a 10 second test recording first; at each question the tutor's windows blink for half a second (the model's capture must not contain the drawings).

## Flow 1: learn (why is the Pythagorean theorem true?)

1. A lecture video on YouTube with a right triangle (5, 12 and an unknown x) is paused on screen.
2. Open the chat (Ctrl+Shift+E if hidden). Type: "Explain why the Pythagorean theorem is true. Prove it."
3. What the viewer sees: the regions flash (it is reading the screen); the first step is typed and the three sides are highlighted; the proof diagram is drawn beside the triangle (a big square, four triangles, a tilted empty square labelled x^2); the triangles slide into their new places and the empty area becomes a square of side 5 and a square of side 12; the last step writes x^2 = 5^2 + 12^2 = 169, x = 13.
4. Follow-up with no hotkey: click the suggested reply, or type "Why is the empty area the same in both pictures?". The drawing stays and the answer carries on.
5. New chat (Ctrl+Shift+N) to finish: the drawings and the conversation are gone.

## Flow 2: be guided (I am lost in a cloud console)

Use a real console the viewer will recognise, up to the final confirm button (never create anything for real), or the web playground sample "Guide me through a cloud console".

1. Open the console's home page. Type: "I am new here. I need an access key for my app. Where do I start?"
2. A box and a short label appear on the exact menu item; the chat says why.
3. Click it yourself and say nothing. The page changes: the old box fades away at once, and a moment later (the page has settled) a quiet line says the screen changed and the next control is boxed. The goal shows at the top of the chat with Following your clicks switched on.
4. On the form: one step per field, the permission to pick and why, a warning that the key is shown only once.
5. Click somewhere wrong on purpose: it says plainly where you ended up and how to get back. Finish the task: it says the task is complete.
6. Pause Following, click around, and show that nothing is said until you resume.

## Good pages to try the guide on (no account needed first)

- AWS Pricing Calculator (calculator.aws) and the Google Cloud pricing calculator: busy, public, no sign-in. Ask how to price one small server.
- Your own AWS console (IAM, Create access key), Nebius Token Factory (Billing), Tavily dashboard, Devpost project submission: stop before the last button.
- The made-up Acme Cloud console in the playground sample, for a repeatable run.

## Things to check before recording

- The two windows do not appear in a capture (check one frame of the recording).
- No stale marks from an earlier run: press Ctrl+Shift+N first.
- The backend answers in a few seconds (the first request after a pause can take about ten); do a dry run.

## Voice version of both flows

Install first (the installer file, or `npm start`: the first start downloads the voice models; wait for "The voice is ready"). The chat stays hidden; the orb is at the bottom left.

1. Say: "Hey Nova, explain why the Pythagorean theorem is true." The orb turns amber, then blue: the first step is drawn and read aloud while the next ones are being written. Say nothing while it plays.
2. Interrupt with a follow-up: "Why is the empty area the same in both pictures?" (within 12 seconds of it speaking, no wake word needed).
3. Say "Open chat" to show the transcript and type something; say "Close chat" to hide it. Say "Hey Nova, new chat" to start over.
4. Guide flow: "Hey Nova, I need an access key for my app. Where do I start?" Then click on the page and say nothing: the old mark fades at once, the next step is read out. Say "I don't see it" or "stop" at any time.

Tips: keep the microphone away from the speakers' loudest side; a video playing on the screen is heard too, which is why the tutor only reacts to the wake word (or Ctrl+Shift+Space).
