# 04: Ask a question and get a drawn answer from the real model

**What to build:** The learner types a question; the backend sends the capture with numbered regions to an NVIDIA vision model on Nebius Token Factory, which chooses regions by number and returns an explanation and shapes anchored to those regions; the overlay draws them with a caption. The model never returns raw pixel coordinates. The model id comes from configuration.

**Blocked by:** 03, 01

**Status:** ready-for-agent

- [x] Model adapter calls Nebius through its OpenAI-compatible API with the model id from configuration (MODEL_NAME, MODEL_BASE_URL, MODEL_API_KEY; default google/gemma-3-27b-it)
- [x] Returned shapes are anchored to region ids plus relative offsets and render correctly at different display scales (arrows now have an explicit tail and head after a real test showed a wrong-direction arrow)
- [ ] A lecture frame and an application window each produce a useful drawn answer end to end (lecture frame: yes, on the real Pythagoras frame the model answers correctly and highlights the exact line and boxes the exact label with DeepSeek-V4.1-Flash; real application window not tried yet; desktop run by a human after the fixes not yet confirmed)
- [x] The answer text appears as a caption (question bar added; needs a human run)
- [x] Tests use recorded model responses and never call the live model (44 backend tests)

## Notes

- NVIDIA vision models (Nemotron-Nano-V2-12b, Cosmos3-Super-Reasoner) are listed in the Nebius catalog with Public endpoint NOT available; only Dedicated endpoint (own GPU, billed by time). The public API cannot call them. Public vision models that work: google/gemma-3-27b-it (default), openbmb/MiniCPM-V-4_5. Qwen3.5-397B and GLM-5.2 reject image input; Kimi-K2.6 returned no JSON at max_tokens 1200.
- Accuracy limit seen on a real frame: small labels inside a figure (the '12', '5', 'x') are not separate regions, so the model can only point within the figure by relative fractions. Candidate fixes: split figures into labels with OpenCV, a better model, or a second look at a crop.
- Decision pending with the owner: deploy a dedicated endpoint for an NVIDIA vision model (cost per hour unknown) or use the hybrid (non-NVIDIA vision + NVIDIA Nemotron text).

## Update after the owner's first real run (photo showed clutter, English text, wrong content)

Findings and fixes:
- Gemma-3-27b-it misread the frame (called 12 the hypotenuse, solved x as sqrt(119)). Five-question comparison on one real frame: DeepSeek-V4.1-Flash and Kimi-K2.6 answered correctly; Kimi is slower (10 to 13 s) and sometimes returned no JSON; MiniCPM-V-4_5 fast but wrong on the solve; GLM-5.2 and Qwen3.5-397B reject images. Default model is now deepseek-ai/DeepSeek-V4.1-Flash (latency varied from 2 s to 47 s across runs).
- Old drawings piled up because every turn kept the previous canvas: each question now starts a fresh drawing until follow-ups are built (ticket 06).
- The explanation leaked region numbers: the prompt now forbids that.
- Positions were imprecise because the model could only give fractions of a large figure region. Fix: the proposer now also finds `line` regions (with end points) and `label` regions inside figures; highlights on a line are drawn along the line; boxes on a label surround it; arrows can target a region exactly (target_region_id).
- OpenCV 5 note: cv2.HoughLinesP returns an (N, 4) array, not (N, 1, 4) as in OpenCV 4.

## Update 2: owner got "502: the model reply has no JSON object"

Cause (verified by reading the raw API response): DeepSeek-V4.1-Flash is a reasoning model. It used the whole 3000-token budget on reasoning (reasoning_tokens 3000, finish_reason length) and returned empty content. It also confused the region numbers drawn on the picture (18, 19, 20) with numbers that are part of the picture (5, 12).

Fixes:
- `reasoning_effort: "none"` for DeepSeek-V4.1-Flash (per-model table MODEL_EXTRA_BODY; override with MODEL_EXTRA_BODY env JSON). Latency now 2 to 3 s, and no empty replies in 11 consecutive real calls. `reasoning_effort: "low"` did NOT help; `chat_template_kwargs.thinking=false` also works.
- Region labels are now R1, R2, ... in the picture and in the list, so they are not mixed up with digits in the picture.
- One retry when the reply is empty or not usable (the bad reply, if any, is shown back with a reminder); the trace records attempts. After two failures the error says what the model said.
- With thinking off, accuracy dropped (said 12 or 5 was the hypotenuse). Fixed mostly by giving the model geometry hints (line orientation: horizontal / vertical / slanted; each label's nearest line) and an `analysis` field written before the explanation; temperature set to 0. Result on the real Pythagoras frame: x, 12, 5 and the whole solve all correct and highlighted on the right lines (x question 3 of 3 runs).
- Still weak: labels' contents are not read (no OCR), so the model identifies x, 5 and 12 only by looking at the picture. Only one real frame has been tried.

## Update 3: owner's second photo (drawings offset upwards, 5 misread as 3, only highlights)

- Offset: the overlay window was 1536x816 DIP instead of the display's 1536x864. On Windows a frameless window is trimmed to the work area (screen minus the taskbar), so SVG drawings were squashed by 5.6 percent vertically (error grows downwards). Fix: enableLargerThanScreen and setBounds(display bounds); verified overlay bounds now equal display bounds (set SCREEN_TUTOR_DEBUG_GEOMETRY=1 to log). Needs the owner to confirm on screen.
- Misread digits: the numbered marks drawn on the picture covered or touched small digits (the 5 became 3). Now the model gets TWO pictures: the clean screenshot for reading, and a marked one with thin outlines and small badges placed beside the regions (no overlaps) for finding labels. On the real frame the solve is correct (x = 13) in three runs.
- Not yet possible (design limit, not a model limit): the drawing vocabulary can only mark things that already exist (box, ellipse, highlight, arrow, label, step number). It cannot draw NEW geometry (squares on the sides, an equation laid out visually) or play an explanation step by step. See the proposed follow-up in the chat: new shapes (polygon, square on a line, text/equation) and multi-step walkthrough (steps with captions, advanced by a hotkey). This belongs in a new ticket.
