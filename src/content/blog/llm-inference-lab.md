---
title: "LLM Inference Lab: Checking Every Fast Path Against a Slow One"
description: "I built a small decoder-only transformer from scratch in NumPy, then re-implemented it in PyTorch and JAX. Every optimisation is checked against a reference, and the benchmark fails the build when it drifts."
publishDate: 2026-11-25
lang: en
key: llm-inference-lab
tags:
  - LLM
  - Inference
  - Python
  - PyTorch
  - JAX
repo: https://github.com/douglasbonafe/llm-inference-lab
---

Most inference demos show a tokens-per-second number and stop there. The number is easy to produce. The hard part is knowing that the fast path still computes what the slow path computes, on every shape you care about, after the next refactor.

So I built the inference side of a small transformer myself, and treated correctness as the thing the benchmark measures first. The code is here: [douglasbonafe/llm-inference-lab](https://github.com/douglasbonafe/llm-inference-lab).

## What is in it

- **Attention, two ways.** A naive reference, and a blockwise kernel that streams over key blocks with a running max and running sum, the same idea behind FlashAttention. The blockwise kernel never builds the full score matrix. Both are tested against each other across block sizes and offsets.
- **KV cache.** Pre-allocated per layer. Cached decoding produces the same logits and the same greedy tokens as recomputing the whole prefix.
- **int8 weights, per channel.** Each output column gets its own scale, so `(x @ q) * scale` equals `x @ (q * scale)`. The tests check the error is within half a quantisation step.
- **Three backends, one set of weights.** NumPy is the reference. PyTorch uses `scaled_dot_product_attention` and has a working Adam training loop. JAX is `jax.jit`-compiled. All three must agree with NumPy within 1e-4.
- **A tokenizer pipeline.** A byte-level BPE tokenizer trained locally with `tokenizers`, wrapped as a `transformers` fast tokenizer, and fed into the cached decoder.
- **A serving probe.** A standard-library client for any OpenAI-compatible `/v1/completions` endpoint.

## Results

Measured on a CPU-only WSL2 machine, with a model of `d_model=64`, 2 layers, 4 heads.

| Check | Difference | Tolerance |
|---|---|---|
| Blockwise vs. reference attention | 6.7e-16 | 1e-4 |
| KV-cached vs. full-sequence logits | 4.0e-7 | 1e-4 |
| PyTorch vs. NumPy logits | 9.0e-7 | 1e-4 |
| JAX vs. NumPy logits | 6.8e-7 | 1e-4 |
| int8 vs. fp32 logits (relative) | 1.1% | 5% |

Performance, with the same caveat that these are small numbers on a laptop-class CPU:

- The KV cache gives about **3,300 tokens/s** on a 32-token prompt generating 64 tokens, **7.7x faster** than recomputing the prefix at each step.
- At sequence length 512, blockwise attention takes **8.8 ms** against **15.8 ms** for the reference. At 128 the two are about even. The blockwise loop has Python overhead that only pays off on longer sequences, and the numbers show that instead of hiding it.
- int8 cuts linear-layer weight memory, but the embeddings stay in fp32, so the total saving at this size is well under 4x.

The benchmark exits non-zero if any correctness check is out of tolerance, so it can gate CI.

## What I did not measure

I did not install or benchmark vLLM, SGLang or llama.cpp. That machine has no GPU and no C++ toolchain. The serving probe is tested against a stub server, and the README gives the commands for pointing it at each real engine. Those numbers are not in this post, and I would not trust a comparison that was not run on the same hardware.

Also out of scope: batching, paged KV memory, CUDA or Triton kernels, and any model with real weights. The outputs are gibberish on purpose. The point is the machinery around the model.

## Running it

```bash
pip install -r requirements.txt   # torch CPU wheels come from the PyTorch index
python -m pytest                  # 39 tests
python -m inference_lab --out results/benchmark.json
```

If you care about inference work, the part I would look at first is the test suite, not the throughput table. A fast kernel that disagrees with the reference is a bug with a good benchmark attached.
