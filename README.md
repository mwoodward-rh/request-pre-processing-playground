# Request Intelligence Lab

A small demonstration of **OpenJev classification + LangExtract semantic extraction**, with a React dashboard. Classification uses a local/private OpenJev service. Extraction uses a server-configured, OpenAI-compatible Chat Completions endpoint by default; adopters bring their own endpoint, model name, and API key. Optional Ollama and Azure Foundry adapters remain available. Enter a request and optional explicit context; inspect intent scores, exact source highlights, semantic attributes, a mention graph, and real model timings.

No Guardian dependency. No database, memory retrieval, persistent chat history, calibration, automatic routing, tool execution, or generated answer. No synthetic inference fallback. Unavailable stages are reported independently.

## Architecture

```text
React dashboard → POST /api/analyze → Python FastAPI
                                       ├─ OpenJev HTTP adapter → typed decision scores
                                       └─ LangExtract process → selected extraction provider (Chat Completions by default)
                         dashboard ← source + scores + spans + timings
```

The model stages run concurrently. The API returns when both settle; the UI shows processing meanwhile. Results live in the current browser page only. Reloading clears them. No cross-request context is accumulated: prior context must be explicitly supplied.

## Quick start

### Recommended: setup once, launch with one command

Install Python 3.12+, Node 20.19+ (or a newer supported Node), and Git (for the pinned Jev package). Configure a BYO endpoint as described below, then from this directory:

```sh
python3.12 scripts/setup.py
python3.12 scripts/launch.py
```

#### Windows (PowerShell)

From the project directory, create `.env` from the example only if you do not already have one, edit it to set your endpoint's model and `OPENAI_API_KEY`, then run:

```powershell
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
py -3.12 scripts\setup.py
py -3.12 scripts\launch.py
```

Keep `.env` local; setup never overwrites it, and it is excluded from the source archive. The launcher prints the local dashboard URL. Press Ctrl+C in that terminal to stop services it started.

Setup installs isolated Python environments, builds the dashboard, and downloads/caches the OpenJev weights. Jev downloads may be several GB and require internet access and acceptance of the model's applicable license. The extraction endpoint is never installed or downloaded. Setup never overwrites `.env`. `--skip-downloads` installs dependencies/builds only (still needs package-registry access), without starting services or downloading weights.

Launch performs no installs or downloads. It validates the configured extraction provider, starts the bundled Jev adapter, and serves the built dashboard. OpenAI-compatible mode validates local configuration but does not probe the endpoint before analysis. It does not start, install, or require Ollama. It prints the browser URL. Ctrl+C stops only its own children; externally selected Jev services are left running. Occupied dashboard/Jev ports produce a failure rather than killing another service. Startup readiness waits up to three minutes for Jev.

`python3.12 scripts/launch.py --check` performs read-only configuration and existing-endpoint checks; it does not start services or perform inference. An unstarted local Jev will correctly fail this check until running.

### BYO endpoint and configuration

Copy `.env.example` to `.env` with your editor and set `OPENAI_API_KEY`, or use server-process environment variables. Precedence is **shell > .env > defaults**. The key is used only by the Python backend; never put it in frontend code or a `VITE_` variable. The scripts accept simple `KEY=value` lines and optional surrounding quotes; there is no shell execution, variable interpolation, or inline-comment processing. Unknown keys are rejected. `.env` is ignored and excluded from source archives.

The endpoint contract is the OpenAI Chat Completions API: configure a base URL such as `https://api.example.com/v1`, a model/deployment identifier, and a bearer API key. Do not include `/chat/completions`, URL credentials, query parameters, or fragments. Remote endpoints require HTTPS; plain HTTP is accepted only on loopback. Provider-specific compatibility varies, so verify that the service accepts standard `messages`, returns one complete assistant text choice, and supports bearer authentication. Requests do not include tools, streaming, retries, or automatic fallback. OpenAI-compatible mode does not make a live readiness request during launch.

```ini
EXTRACTION_PROVIDER=openai
EXTRACTION_MODEL=your-model-or-deployment
OPENAI_BASE_URL=https://your-provider.example/v1
OPENAI_API_KEY=your-server-side-key
```

Never include a real key in a shared `.env.example`, source archive, screenshot, or commit. The checked-in example contains no credential.

```sh
# Use an existing compatible Jev endpoint and matching local tokenizer:
JEV_MODE=external JEV_URL=http://192.168.1.20:8022 \
JEV_TOKENIZER=/path/to/tokenizer.json python3.12 scripts/launch.py

# Change the dashboard port if another instance is running:
LAB_PORT=8031 python3.12 scripts/launch.py
```

`JEV_MODEL` selects the Hugging Face repository downloaded by setup; `JEV_MODEL_PATH` selects the loaded snapshot; `JEV_TOKENIZER` must match it (defaults to the model path's tokenizer.json when not explicitly set). Jev replacements must retain the OpenJev architecture/head and question contract—this is not an arbitrary chat-model selector. `JEV_DEVICE=cpu` is the default. Stop/restart the launcher after changing settings.

When downloading a different Jev checkpoint, choose a separate `JEV_MODEL_PATH` and update/remove the explicit `JEV_TOKENIZER` setting so snapshots and tokenizer files do not get mixed.

The setup downloader fetches Jev weights only. A remote Jev endpoint is never launched or stopped, and its tokenizer must be supplied locally.

### Optional Azure Foundry extraction

Set these values in `.env`, then restart the launcher:

```ini
EXTRACTION_PROVIDER=foundry
EXTRACTION_MODEL=your-agent-name
FOUNDRY_ENDPOINT=https://your-resource.services.ai.azure.com/api/projects/your-project/agents/your-agent-name/endpoint/protocols/openai/responses
FOUNDRY_API_VERSION=2025-11-15-preview
```

The endpoint is an **agent Responses endpoint**, not a Chat Completions base URL. Omit its query string; the API version is configured separately. `EXTRACTION_MODEL` labels the agent in results; it does not change the model deployed behind that agent. The agent's existing instructions can affect extraction quality. A dedicated extraction agent without tools is preferable to a general-purpose agent.

Install Azure CLI and sign in to an account authorized for the project. Authentication obtains an Azure CLI token for `https://ai.azure.com`; no key or token belongs in `.env` or frontend code. On Windows the adapter uses Azure CLI's bundled Python and, if present, the existing `%LOCALAPPDATA%/FoundryDiagnostics/pywin32-py313` DLL repair used by the companion Foundry client. Other systems use `az` on PATH. Authentication failures require fixing the CLI installation/login, not disabling certificate validation.

Foundry mode validates Azure CLI authentication and requires no local extraction model. Jev still runs locally by default. `launch.py --check` validates configuration and Azure authentication, but does not submit inference or prove permission to invoke the agent.

**Remote data boundary:** the current request and explicit context are sent to Azure Foundry along with LangExtract's extraction instructions and examples. Requests set `tool_choice=none` and do not send a conversation or previous response ID. Actual tool-call/approval outputs are rejected. Foundry may still perform configured MCP tool discovery and return `mcp_list_tools` metadata. These settings do not guarantee zero server-side storage: Azure/agent retention and logging policies still apply. Use synthetic or approved non-sensitive text.

The app still aligns returned spans against the exact source and reports partial failures without a fallback. A completed response can contain no useful extractions. Compare measured latency and grounded spans on representative prompts; remote inference is not automatically faster than a small local model.

### Optional local Ollama extraction

To use Ollama instead of BYO OpenAI, set `EXTRACTION_PROVIDER=ollama`, set `EXTRACTION_MODEL` to an installed model, and optionally configure `EXTRACTION_URL`. Only this mode may start the default local Ollama service when `OLLAMA_AUTOSTART=1`. Setup downloads the selected Ollama model only when downloads are enabled. Ollama model selection and quality are the adopter's responsibility. Endpoint locality alone cannot prove a model is locally executed; choose a local model, not a cloud-backed alias.

### Manual setup (alternative)

Requirements: Node 20.19+ (or newer supported Node) and Python 3.12+. Run commands from this directory.

```sh
python3.12 -m venv .venv
.venv/bin/pip install -r requirements.txt
npm ci
```

### 1. OpenJev

If you already have a compatible local `/v1/systemone` service, set `JEV_URL` and use its matching `tokenizer.json`. Otherwise install and run the included adapter:

```sh
python3.12 -m venv .venv-jev
.venv-jev/bin/pip install -r requirements-jev.txt
.venv-jev/bin/hf download com-kotobalabs/open-jev-deberta-v3-large --local-dir models/open-jev
JEV_MODEL_PATH=models/open-jev JEV_DEVICE=cpu \
  .venv-jev/bin/uvicorn backend.jev_server:app --host 127.0.0.1 --port 8022 --no-access-log
```

The optional inference package is pinned to an upstream commit. Keep its environment separate: its Transformers dependency requires an older tokenizer runtime than the analysis worker. Model download is explicit and separate; weights are not bundled. CPU is the conservative default. First model loading can take time and substantial RAM. The adapter is for this local demo only, not a public inference service.

### 2. Run the API and dashboard

Ensure the server process has the BYO endpoint variables, including `OPENAI_API_KEY`, and Jev is available. Manual uvicorn does not load `.env`; use the launcher to load `.env` automatically. Then, in one terminal:

```sh
.venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8030 --no-access-log
```

In another:

```sh
npm run dev
```

Open **http://127.0.0.1:5186**. The Vite proxy talks only to the standalone API, not Guardian. The manual uvicorn commands do not load `.env`; export variables or use the launcher above. Never put service credentials in `VITE_` variables. Avoid typing real credentials into shell history; prefer the ignored local `.env` file or your process manager's secret configuration.

Alternatively, `npm run build`, then start/restart the Python API; it serves `dist/` at **http://127.0.0.1:8030**. This single-origin built mode does not require the Vite dev server.

## What the scores mean

- Jev's fixed intent taxonomy: explain, research, create, modify, troubleshoot, recall, execute, monitor, other.
- Additional questions assess references to prior work, multiple tasks, and noise/episodic/durable memory value. These are only assessments, not actual retrieval or storage decisions.
- Current text is chunked using the model tokenizer: 220 tokens without context, 130 with context; up to 32 chunks. Prior context uses its last 70 tokens. The UI reports truncation. Full explicit context goes to LangExtract, bounded by input character limits.
- Intent and signal scores are averaged across chunks; reference/task flags use the maximum. This aggregation can dilute localized intents. No claim of full-history reasoning or calibrated accuracy is made.
- A top score below 0.60 or a top-two margin below 0.15 is marked uncertain. These thresholds are illustrative.
- LangExtract receives the source as untrusted data and returns exact spans in six categories. Mismatched/out-of-bounds spans are rejected. Browser offsets are UTF-16; semantic attributes remain model interpretations.
- The graph is a view of source mentions, not a persistent ontology or verified relationship inference. Timings measure this run, not benchmark promises. Complexity is not assessed.

## Privacy and security boundaries

Use synthetic or non-sensitive prompts. **This slim example does not redact secrets or PII.** Source text is sent to the configured Jev and extraction services and returned to the browser. In OpenAI-compatible and Foundry modes, extraction text, explicit context, LangExtract instructions, and examples go to the configured remote provider. The application does not persist or log prompts, but model servers, provider services, operating systems, or reverse proxies may have their own logging and retention policies.

Model URLs and API keys are server-owned configuration. Jev and Ollama URLs are checked for local/private addresses; OpenAI-compatible endpoints require HTTPS except on loopback; Foundry requires an explicit HTTPS Azure agent Responses URL. Remote adapters do not follow redirects. There is no automatic hosted fallback. These checks are guardrails, not an egress firewall against malicious DNS, proxy configurations, or model servers. Use trusted endpoints. The API binds to loopback by the documented commands and checks browser origins. Do not expose either Python server or the Vite server publicly; there is no multi-user authentication or tenant isolation. Add proper authentication, limits, deployment hardening, and a data policy before shared hosting.

One analysis is admitted at a time; extra requests receive 429. Input is bounded; extraction subprocesses have a deadline and are killed on timeout. Model failure produces a partial/failed result without reflecting upstream error payloads or inserting heuristic predictions. API health is not model health.

## Verification

```sh
.venv/bin/pip install -r requirements-test.txt
.venv/bin/python -m pytest tests
npm test
npm run build
gitleaks dir . --redact
```

Tests exercise real HTTP validation with mocked inference, partial failures, error privacy, concurrency, Unicode span grounding, and score aggregation. Model-quality evaluation is separate. A live smoke run should use a synthetic prompt and require both stages complete; inspect returned model IDs and actual spans.

Development acceptance (2026-09-24): the built dashboard and standalone Python API completed a browser-submitted synthetic request against existing local OpenJev and Gemma services. Jev took 761 ms; LangExtract took 25,431 ms and returned two grounded spans with one rejected span. A different request returned no spans, so empty extraction is surfaced explicitly. These are individual observations, not benchmarks or quality guarantees. The optional bundled Jev adapter has contract tests and dependency-resolution checks; a fresh model download/start is not part of this acceptance run.

Launcher acceptance: external-endpoint readiness checks passed, the launcher served API and dashboard HTTP 200 on a separate loopback port, and Ctrl+C stopped the owned API process. Existing model services remained available. Setup's external-mode `--skip-downloads` path completed. Configuration precedence, invalid values, model-presence checks, process ownership, custom-port origin checks, and no-download setup behavior are covered by tests. Fresh multi-GB downloads, local Jev model loading, and automatic startup of a previously stopped Ollama have not been exercised in this acceptance run.

## Sharing and attribution

This directory is intended to become a fresh standalone repository. Do **not** publish its parent workspace or private Git history. Exclude ignored environments, model files, screenshots, and any local artifacts. Select a project license before public release; none is presumed here. No repository has been created or published by setup.

Run `.venv/bin/python scripts/package.py` to produce `artifacts/request-intelligence-lab-source.zip` from an explicit source-file allowlist. This intentionally excludes the parent workspace, runtime configuration, virtual environments, dependencies, and model weights. Choose the application license before public release and add it to the packaging allowlist.

- [OpenJev model card](https://huggingface.co/com-kotobalabs/open-jev-deberta-v3-large): independent typed-decision reproduction; model card declares Apache-2.0. Not affiliated with TypeSafe AI.
- [typed-decisions inference implementation](https://github.com/kotoba-lang/typed-decisions): Apache-2.0 metadata; installed separately, not vendored.
- [LangExtract](https://github.com/google/langextract): Apache-2.0; installed separately.
- React (MIT), Vite (MIT), FastAPI (MIT), Uvicorn (BSD-3-Clause), and their dependencies retain their respective licenses. Model licenses are separate from this application; verify the selected extraction model's terms before redistribution.

No private prompts, labels, databases, model weights, or infrastructure configuration are included in the example source.
