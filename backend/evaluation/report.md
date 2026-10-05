# Region-pick evaluation

31 synthetic cases (right triangles in four orientations and two themes, toolbars, bullet slides). **Pointed** = a shape drawn at any step sits on the region the answer must point at (for a triangle side: the line region with the same end points, or a label right beside it); **keyword** = the explanation contains the expected fact (where one is expected). Live models on Nebius Token Factory.

First run, 2026-10-03 (all six models, before the answer was drawn in steps):

| Model | Cases | Pointed correctly | Keyword correct | Failed | Retried | Median seconds | Pointed by kind |
|---|---|---|---|---|---|---|---|
| deepseek-ai/DeepSeek-V4.1-Flash | 31 | 31/31 | 11/12 | 0 | 0 | 2.6 | bullets 6/6, toolbar 7/7, triangle 18/18 |
| google/gemma-3-27b-it | 31 | 26/29 | 7/10 | 2 | 0 | 3.5 | bullets 6/6, toolbar 7/7, triangle 13/16 |
| openbmb/MiniCPM-V-4_5 | 31 | 25/30 | 6/11 | 1 | 0 | 2.3 | bullets 6/6, toolbar 7/7, triangle 12/17 |
| moonshotai/Kimi-K2.6 | 31 | 27/27 | 8/8 | 4 | 2 | 6.0 | bullets 6/6, toolbar 7/7, triangle 14/14 |
| Qwen/Qwen3.8-27B | 31 | 31/31 | 12/12 | 0 | 0 | 2.4 | bullets 6/6, toolbar 7/7, triangle 18/18 |
| zai-org/GLM-5.3-Flash | 31 | 31/31 | 11/12 | 0 | 2 | 5.9 | bullets 6/6, toolbar 7/7, triangle 18/18 |

Re-run, 2026-10-04, after the chat, the guide prompt, line-level text regions and pointing marks that go away (the two models in use; pointing is now scored over every shape drawn in the turn, because a mark can be taken off by a later step):

| Model | Cases | Pointed correctly | Keyword correct | Failed | Retried | Median seconds | Pointed by kind |
|---|---|---|---|---|---|---|---|
| deepseek-ai/DeepSeek-V4.1-Flash | 31 | 31/31 | 10/12 | 0 | 0 | 3.1 | bullets 6/6, toolbar 7/7, triangle 18/18 |
| Qwen/Qwen3.8-27B | 31 | 30/31 | 10/12 | 0 | 0 | 2.3 | bullets 6/6, toolbar 7/7, triangle 17/18 |

DeepSeek-V4.1-Flash is the default and Qwen3.8-27B the second model asked when the first is slow (hedged requests). The cases are synthetic and easy: they separate weak models from strong ones, not real-world accuracy. The keyword check varies by one or two between runs of the same model.

Re-run after small line drawings were made detectable (same two models, same result): DeepSeek-V4.1-Flash 31/31 pointed, 11/12 keyword; Qwen3.8-27B 30/31 pointed, 10/12 keyword.
