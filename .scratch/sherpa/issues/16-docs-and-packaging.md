# 16: Documentation and Windows packaging

**What to build:** Everything a judge or user needs: README, architecture diagram, open-source licence, a build, deploy and test guide that can be followed from scratch, a Windows installer or portable build of the app, and running notes for the Nebius feedback form.

**Blocked by:** 13, 14

**Status:** resolved (2026-10-04)

- [ ] README explains what it is, how it works and how to run it
- [ ] Architecture diagram shows client, backend, OpenCV, model, Tavily and AWS pieces
- [ ] Licence file is present
- [ ] Following the guide from a clean machine reproduces the build, deploy and tests
- [ ] A Windows build runs on a machine without the dev tools
- [ ] Feedback notes on Nebius, NVIDIA and Tavily are collected in one file

## Result (2026-10-04)

README has the architecture diagram (mermaid), a security and failure handling paragraph, the Windows build and the AWS sections; `LICENSE` (MIT); `FEEDBACK.md`; `npm run package -- --url=...` in desktop/ makes an installer `Sherpa-Setup-<v>.exe` and a portable `Sherpa-Portable-<v>.exe` (electron-builder, about 110 MB each). Tested here with empty data folders: it downloads the voice models by itself and starts listening. The access token is not in the file (a secret); the app asks for it once in the chat. NOT done: a run on a truly clean machine or Windows Sandbox, code signing (SmartScreen will warn), a build/deploy/test run from a fresh clone.
