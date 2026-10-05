# Feedback notes (for the Nebius, NVIDIA and Tavily forms)

Collected while building screen-tutor, 2026-10-03 to 2026-10-04. Facts only; each line says what was seen.

## Nebius Token Factory

Good:
- OpenAI-compatible API (`https://api.tokenfactory.nebius.com/v1`): the existing client code worked unchanged; switching models is one string.
- Fast: DeepSeek-V4.1-Flash and Qwen3.8-27B answered a full vision turn (image, 70 numbered regions, conversation) in a median of 2.3 to 3.1 s on our 31-case evaluation (`backend/evaluation/report.md`).
- Many strong vision-capable models behind one key made it cheap to compare six models on the same cases in an afternoon.
- Streaming works, which let steps be drawn while the model was still writing.

Friction:
- DeepSeek-V4.1-Flash is a reasoning model: with the default settings it spent its whole token budget thinking and returned an empty answer (our 502s). Fix was `reasoning_effort: "none"` through the request body; this was found by trial and is not obvious from the model list. A per-model note on reasoning defaults in the catalog would have saved time.
- Latency of the same model varied from 2 s to 47 s between calls on the same day. We now ask a second model if the first has not produced a step after 4 s (hedged requests), which hides most of it.
- Catalog and API differ: the NVIDIA vision models shown on the catalog page (Nemotron-Nano-V2-12b, Cosmos3-Super-Reasoner, Nemotron-3-Nano-Omni) returned 404 for the ids we guessed, and the model list endpoint shows only NVIDIA text models. The page says nothing about needing a dedicated endpoint. The exact API id (or a copy button) next to each catalog entry would help.
- No speech models in the catalog (we use local whisper.cpp and Piper for a fully local voice).
- The $1 trial credit was too small for real evaluation runs; the Devpost code fixed that, but the trial-to-code step was a surprise.

## NVIDIA models

- Used in the product: **nvidia/nemotron-3-super-120b-a12b** rewrites each step's caption as natural speech (`/narrate`). On 9 real captions it answered in a median of 0.8 s; about 7 of 9 rewrites passed our checks (the rest fell back to the caption).
- Behaviour worth knowing: with default settings the Nemotron models spend the token budget on reasoning (the 30B and Lightning models returned no text within 400 tokens; Super took 2.5 s and returned empty content at 300). `reasoning_effort: "none"` gave 0.7 s and clean text. A note about this in the catalog would help.
- Faithfulness: given the learner's question as context, it drew a wrong conclusion ("nothing is wrong") for a step about a bug; without the question and with an instruction not to add claims it stayed faithful, but a looser prompt invented a fact (a key "already exists"). We therefore only let it rephrase, and check numbers and length.
- Not used: the NVIDIA vision models (Nemotron-Nano-V2-12b, Cosmos3-Super-Reasoner) returned 404 for the ids we tried and appear to need a dedicated endpoint. The picture is still read by DeepSeek / Qwen, with OpenCV regions to pick from (gemma-3-27b picked correct regions for coarse questions and failed on fine ones such as one digit in a figure).

## Tavily

- Used as a runtime call: when a question needs facts that are not on the screen, the model can ask for a web lookup and the answer cites the sources (the chat shows source links).
- Integration was a single HTTP call.
- Latency adds a second round trip to a turn, so it is only used when the model asks for it.

## AWS (for the OpenCV COOL award)

- Lambda container on Graviton (arm64) with Lambda Web Adapter ran an unchanged FastAPI app with OpenCV 5; response streaming needed both the Function URL invoke mode `RESPONSE_STREAM` and `AWS_LWA_INVOKE_MODE=response_stream`.
- Measured: 22 % cheaper per turn than x86 and about 4 % faster for the OpenCV work (`backend/evaluation/benchmark.md`).
- First arm64 image build on an x86 laptop took about 10 minutes under emulation; the Dockerfile now caches the dependency layer so later rebuilds only copy the code.
