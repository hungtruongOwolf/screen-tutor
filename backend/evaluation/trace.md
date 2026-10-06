# Decision trace

Model `deepseek-ai/DeepSeek-V4.1-Flash`; live run of the guide loop on the made-up Acme Cloud console (`tools/trace.py`).
Each turn shows what OpenCV 5 found on the new screen and what the agent decided because of it.

### from-the-dashboard

A newcomer on the dashboard asks for an access key; the tutor guides click by click through three pages.

**Turn 1** (the learner asks; frame `console1.png`)

- OpenCV 5 proposed 66 regions: 28 text, 24 detail, 7 ink, 5 control, 1 screen, 1 image.
- The answer points at: box on region 18 (text, box 21,305 109x15).
- Verdict: `continue`. Goal kept: Create a new user in acme.cloud that can use an access key for programmatic access.
- Said: "You are on the Dashboard. To create a user with programmatic access, start in the SECURITY section of the left menu — click 'Access & Identity'."

**Turn 2** (automatic, the screen changed; frame `console2.png`)

- OpenCV 5 proposed 66 regions: 28 text, 23 detail, 9 ink, 4 control, 1 screen, 1 image.
- Of the 34 regions of the previous screen, 11 are still here (same perceptual hash): the page is a different one.
- The answer points at: box on region 15 (control, box 1143,208 108x39).
- Verdict: `continue`. Goal kept: Create a new user in acme.cloud that can use an access key for programmatic access.
- Said: "You are in the right place: the Users tab is open and the list shows two users. Now click 'Create user' at the top right to start a new user."

**Turn 3** (automatic, the screen changed; frame `console3.png`)

- OpenCV 5 proposed 74 regions: 23 detail, 22 text, 10 ink, 6 line, 6 label, 4 control, 1 screen, 1 image, 1 figure.
- Of the 33 regions of the previous screen, 14 are still here (same perceptual hash): the page is a different one.
- The answer points at: box on region 16 (control, box 272,266 382x42); box on region 27 (label, box 276,392 15x15); arrow on region 29 (line, box 303,397 371x6); box on region 33 (label, box 277,469 15x15); box on region 40 (control, box 1113,583 115x40).
- Verdict: `continue`. Goal kept: Create a new user in acme.cloud that can use an access key for programmatic access.
- Said: "The Create user form is open. First type a name for the new user in the User name field — letters, numbers and dashes only."

### goes-back

The learner clicks the wrong way (back to the dashboard): the tutor must say so and lead back.

**Turn 1** (the learner asks; frame `console2.png`)

- OpenCV 5 proposed 66 regions: 28 text, 23 detail, 9 ink, 4 control, 1 screen, 1 image.
- The answer points at: box on region 15 (control, box 1143,208 108x39).
- Verdict: `continue`. Goal kept: Create a new user with programmatic (access key) access
- Said: "You are on Access & Identity > Users. To make a user that can use an access key, click Create user at the top right."

**Turn 2** (automatic, the screen changed; frame `console1.png`)

- OpenCV 5 proposed 66 regions: 28 text, 24 detail, 7 ink, 5 control, 1 screen, 1 image.
- Of the 33 regions of the previous screen, 11 are still here (same perceptual hash): the page is a different one.
- The answer points at: box on region 18 (text, box 21,305 109x15).
- Verdict: `off_track`. Goal kept: Create a new user with programmatic (access key) access
- Said: "We are back on the Dashboard, so the Users page is not open. Click Access & Identity in the left menu to get back to it."
