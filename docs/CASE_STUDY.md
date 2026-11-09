# DXPX Helper: recovery and outcome verification

## Context

This is a Windows desktop helper for a specific university training website, with separate workflows for two training categories. Real usage exposed paused-player dialogs, stalled playback, page changes and a mismatch between local playback and server-side completion. The implementation was developed with AI coding assistance; upstream references and question data are attributed in [ATTRIBUTION.md](../ATTRIBUTION.md).

## Engineering decisions

| Problem | Implementation | Evidence |
| --- | --- | --- |
| Browser setup and session handling | Dedicated Chrome/Edge profiles, dynamic local debugging port, CDP connection | `ensure_browser`, `CDP` in `src/core.py` |
| Blocking UI or competing instances | Worker thread, message queue, cooperative cancellation, per-category Windows mutex | `App` in `src/app.py` |
| Repeated stalls | Injected observation time, a 10-second threshold and at most two reloads per resource | `StallGuard` and `tests/test_playback.py` |
| False completion | Re-read formal platform state; distinguish accepted requests from completed work | `Client.run_videos`, `run_playback` and core tests |
| Changed option order | Normalize full contents and map to current option IDs; reject ambiguity | `resolve` and reordered-options test |
| Distribution and diagnosis | PyInstaller directory build, local structured logs and feedback | `build.py`, `App.feedback` |

## Reproduce without an account

After installing `requirements.txt` on Windows with Python 3.11:

```powershell
python examples/offline_demo.py
python -m unittest discover -s tests -p "test_*.py" -v
```

The four demo scenarios exercise production decision logic with synthetic inputs and block HTTP requests, WebSocket connections and process creation. The existing 17 unit/GUI tests use mocks or synthetic data. They do not constitute a live-platform compatibility test or a coverage percentage.

## Important trade-offs

CDP reduces driver distribution work but ties the tool to Chromium. DOM selectors and request parsing remain website-specific. Cancellation is cooperative and cannot instantly abort an in-flight synchronous request. The mutex is local and category-scoped, not an account-aware distributed lock. Skipping completed work and avoiding POST retries is not a server-backed exactly-once guarantee.

The application includes a direct-record submission path for one category and answer-filling assistance. These are distinct from normal playback and must not be described as passive observation or guaranteed legitimate completion. The offline demo does not invoke a real platform action.

## Relevance to embedded tooling

Time-based state machines, bounded retries, transport/application outcome separation, deterministic tests and diagnostic traces are useful engineering habits for host-side device tooling. This repository does **not** demonstrate C/C++ firmware, RTOS scheduling, ISR safety, peripheral drivers, radio-stack development or on-device timing measurements. Python threads are not evidence of FreeRTOS competence.

Potential next steps include separating transport and page adapters, extending page-variant fixtures and validating distribution on clean Windows machines. None is claimed as already completed.
