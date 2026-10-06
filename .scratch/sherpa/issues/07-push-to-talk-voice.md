# 07: Ask by voice

**What to build:** Hold a key to speak, release to send. Speech is transcribed locally with whisper.cpp so the voice never leaves the machine. A text box remains as a fallback. Nothing is recorded unless the key is held.

**Blocked by:** 02

**Status:** ready-for-agent

- [ ] Holding the key records and releasing it triggers a turn with the transcript as the question
- [ ] Transcription runs locally with no network call and no account
- [ ] A text input path works when speech is unavailable
- [ ] The microphone is never open unless the key is held
- [ ] Setup instructions for the speech model are in the README
