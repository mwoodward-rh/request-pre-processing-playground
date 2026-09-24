# Request Intelligence Lab

A small, local-first demonstration of **OpenJev classification + LangExtract semantic extraction**, with a React dashboard. Enter a request and optional explicit context; inspect intent scores, exact source highlights, semantic attributes, a mention graph, and real model timings.

No Guardian dependency. No database, memory retrieval, persistent chat history, calibration, automatic routing, tool execution, or generated answer. No synthetic inference fallback. Unavailable stages are reported independently.

## Architecture

```text
React dashboard → POST /api/analyze → Python FastAPI
                                       ├─ OpenJev HTTP adapter → typed decision scores
                                       └─ LangExtract process → local Ollama-compatible LLM
                         dashboard ← source + scores + spans + timings
```

The model stages run concurrently. The API returns when both settle; the UI shows processing meanwhile. Results live in the current browser page only. Reloading clears them. No cross-request context is accumulated: prior context must be explicitly supplied.

## Quick start

### Recommended: setup once, launch with one command

Install Python 3.12+, Node 20.19+ (or a newer supported Node), Git (for the pinned Jev package), and Ollama from its official installer. Then, from this directory:

```sh
python3.12 scripts/setup.py
python3.12 scripts/launch.py
```

Setup installs two isolated Python environments, builds the dashboard, downloads/caches the OpenJev weights, and pulls the configured extraction model through Ollama. Downloads may be several GB and require internet access and acceptance of the model's applicable license. Setup never overwrites `.env`. `--skip-downloads` installs dependencies/builds only (still needs package-registry access), without starting Ollama or downloading weights.

Launch performs no installs or downloads. It starts the bundled Jev adapter, starts Ollama only if the default loopback endpoint is unavailable, verifies the selected extraction model is installed, and serves the built dashboard. It prints the browser URL. Ctrl+C stops only its own children; an existing Ollama or externally selected Jev service is left running. Occupied dashboard/Jev ports produce a failure rather than killing another service. Startup readiness waits up to three minutes for Jev.

`python3.12 scripts/launch.py --check` performs read-only configuration and existing-endpoint checks; it does not start services or perform inference. An unstarted local Jev will correctly fail this check until running.

### Configuration and swapping dependencies

Copy `.env.example` to `.env` with your editor, or use shell variables. Precedence is **shell > .env > defaults**. The scripts accept simple `KEY=value` lines and optional surrounding quotes; there is no shell execution, variable interpolation, or inline-comment processing. Unknown keys are rejected. `.env` is ignored and excluded from source archives.

```sh
# Use another model that is already installed in your local Ollama:
EXTRACTION_MODEL=your-model:tag python3.12 scripts/launch.py

# Use an existing private-network Ollama-compatible service:
EXTRACTION_URL=http://192.168.1.20:11434 OLLAMA_AUTOSTART=0 \
  python3.12 scripts/launch.py

# Use an existing compatible Jev endpoint and matching local tokenizer:
JEV_MODE=external JEV_URL=http://192.168.1.20:8022 \
JEV_TOKENIZER=/path/to/tokenizer.json python3.12 scripts/launch.py

# Change the dashboard port if another instance is running:
LAB_PORT=8031 python3.12 scripts/launch.py
```

`JEV_MODEL` selects the Hugging Face repository downloaded by setup; `JEV_MODEL_PATH` selects the loaded snapshot; `JEV_TOKENIZER` must match it (defaults to the model path's tokenizer.json when not explicitly set). Jev replacements must retain the OpenJev architecture/head and question contract—this is not an arbitrary chat-model selector. `JEV_DEVICE=cpu` is the default. `EXTRACTION_MODEL` can select other locally installed Ollama models, with potentially different extraction quality. Stop/restart the launcher after changing settings.

When downloading a different Jev checkpoint, choose a separate `JEV_MODEL_PATH` and update/remove the explicit `JEV_TOKENIZER` setting so snapshots and tokenizer files do not get mixed. Endpoint locality alone cannot prove an Ollama model is locally executed; choose a local model, not a cloud-backed alias.

Setup may pull a model into your explicitly configured Ollama endpoint. Use `--skip-downloads` if that endpoint is managed separately. A remote Jev endpoint is never launched or stopped, and its tokenizer must be supplied locally.

### Manual setup (alternative)

Requirements: Node 20.19+ (or newer supported Node), Python 3.12+, and local model services. Run commands from this directory.

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

### 2. Extraction model

Start Ollama (or a compatible local service) and install a model you are licensed to use. For example, with the extraction model used during development:

```sh
ollama pull gemma4:e4b
```

Use `EXTRACTION_MODEL` to select another already-installed local model. Extraction quality and latency depend on the model. LangExtract is the library; the configured LLM performs extraction. This app does not select a Gemini provider or use a Google API key. LangExtract's dependencies may include cloud SDKs; their presence does not mean they are invoked.

### 3. Run the API and dashboard

In one terminal:

```sh
JEV_URL=http://127.0.0.1:8022 \
JEV_TOKENIZER=models/open-jev/tokenizer.json \
EXTRACTION_URL=http://127.0.0.1:11434 \
EXTRACTION_MODEL=gemma4:e4b \
  .venv/bin/uvicorn backend.app:app --host 127.0.0.1 --port 8030 --no-access-log
```

In another:

```sh
npm run dev
```

Open **http://127.0.0.1:5186**. The Vite proxy talks only to the standalone API, not Guardian. The manual uvicorn commands do not load `.env`; export variables or use the launcher above. Never put service credentials in `VITE_` variables.

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

Use synthetic or non-sensitive prompts. **This slim example does not redact secrets or PII.** Source text is sent to the configured local services and returned to the browser. The application does not persist or log prompts, but model servers, operating systems, or reverse proxies may have their own logging policies.

Model URLs are server-owned configuration, checked for local/private addresses; no hosted fallback exists. This check is a guardrail, not an egress firewall against malicious DNS, proxy configurations, or model servers. Use trusted local endpoints. The API binds to loopback by the documented commands and checks browser origins. Do not expose either Python server or the Vite server publicly; there is no multi-user authentication or tenant isolation. Add proper authentication, limits, deployment hardening, and a data policy before shared hosting.

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
