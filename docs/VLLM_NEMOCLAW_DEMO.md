# vLLM + NemoClaw validation

Agent 2 fetches live signals, asks Nemotron to turn them into grounded content opportunities, and returns a structured result. Its live-data capability is constrained by a NemoClaw/OpenShell allowlist policy.

## Architecture

```text
heartbeat / Agent 2
  -> approved live sources (OpenShell policy)
  -> ResearchAgent structured-analysis request
  -> OpenAI-compatible inference endpoint
  -> NVIDIA Nemotron served locally by vLLM
```

`INFERENCE_BASE_URL` selects an OpenAI-compatible endpoint. When it is unset, Agent 2 keeps its Ollama-compatible local fallback.

## Tested RTX 4070 Laptop profile (8 GB)

NVIDIA Nemotron 3 Nano 4B FP8 is the tested model. The 30B Ollama model is not suitable for fully GPU-resident vLLM inference on this GPU.

Run from WSL after Docker Desktop starts:

```bash
docker run -d --name creator-vllm --gpus all --ipc=host -p 8000:8000 \
  -v ~/.cache/huggingface:/root/.cache/huggingface \
  vllm/vllm-openai:latest \
  --model nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8 \
  --trust-remote-code \
  --gpu-memory-utilization 0.84 \
  --max-model-len 1952 \
  --max-num-seqs 4 \
  --enforce-eager \
  --served-model-name nemotron-3-nano-4b
```

The 84% cap accounts for GPU memory already consumed by NemoClaw/OpenShell. FP8 weights plus FP8 KV cache leave about 1.25 GiB of KV cache (about 23k tokens). vLLM retains asynchronous scheduling and chunked prefill. Eager execution is required because CUDA graphs would consume the remaining KV-cache budget.

Verify:

```bash
curl http://localhost:8000/v1/models
curl http://localhost:8000/health
```

Route Agent 2 from a process that can reach the endpoint:

```bash
export INFERENCE_BASE_URL=http://localhost:8000/v1
export OLLAMA_MODEL=nemotron-3-nano-4b
```

## NemoClaw / OpenShell boundary

Apply the policy:

```bash
nemoclaw my-assistant policy-add --from-file nemoclaw/creator-intel-sources.yaml --yes
```

The policy permits only read operations for Agent 2's sources (Reddit, Hacker News, Google Trends, GitHub Trending, NVIDIA RSS, YouTube, and Tavily), plus approved Python runtimes. It prohibits arbitrary internet access, write actions, credential exfiltration, and unapproved endpoints.

Run the smoke check:

```bash
nemoclaw my-assistant exec --workdir /sandbox/creator-intel -- \
  /sandbox/.venv/bin/python agent2_sandbox_smoke.py
```

A sandbox request to an unapproved host such as `https://example.com` must be denied by OpenShell.

## Demonstrated validation

- vLLM 0.25.1 served `nvidia/NVIDIA-Nemotron-3-Nano-4B-FP8` on the RTX 4070 Laptop through `/v1/chat/completions`.
- Agent 2 fetched a live Hacker News signal and produced structured analysis through that vLLM endpoint.
- The Agent 2 smoke workflow ran inside the NemoClaw sandbox under the allowlist policy.
- OpenShell denied an attempted request to `example.com` because it was not in the policy.

This substantiates the vLLM bounty (real self-hosted inference in the agent path), the Nemotron bounty (Nemotron performs core research analysis), and the NemoClaw + OpenShell bounty (live-source power is constrained by a tested policy).
