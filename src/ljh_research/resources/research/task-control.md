# Task control through the public contract

All requests use `{protocol_version:1, request_id?, project_root, method, params}`. Responses carry `ok` and either `result` or a structured `error` (`code`, `message`, `details`). UTF-8 JSON only is emitted on CLI stdout. The local HTTP adapter binds a project once and does not accept project switching in a request.

## Basic sequence

1. `workspace.get`, `settings.get`: inspect conventions, scientific cards and capabilities.
2. `task.create`: draft a task and its concrete pending authorization request.
3. After direct user confirmation, `decision.resolve` (`approved` / `rejected`) through an actual human entry.
4. `task.claim` with a stable driver ID. Preserve the returned lease privately and call `task.heartbeat` while active.
5. `file.read`, `file.write`, `knowledge.invoke`, `run.submit`, `run.refresh`, `run.logs`, `evidence.record`, `reasoning.reserve`.
6. `task.complete` records a qualified result after runs are reconciled; `task.finish` seals a failed/blocked task. `decision.request` suspends for a user decision; `task.pause` stops new scheduling. For explicit task termination use `task.stop`, which fences ownership and cancels all unfinished task runs. Its `stopping` response is not verified termination: refresh outstanding runs, retaining unknowns for human reconciliation. Legacy `task.cancel` only cancels scheduling and preserves processes.

A file update requires the `expected_sha256` from a preceding read. `run.submit` requires an idempotency `request_key`, argv array and authorized existing cwd. A repeat may not silently change argv, cwd or timeout. A run reservation counts once even if submission becomes uncertain: inspect it rather than consuming another slot.

`task.claim` with `takeover=true` requires explicit human confirmation when the previous owner still has a lease. The new ownership epoch invalidates old leases. Do not expose lease tokens to reasoning providers or in public projections.

## Reference controller and panel

The independently installed `ljh-research-controller` package calls only `ljh_research.public`. Reasoning bindings support generic command JSON, Codex CLI and Claude Code. Providers return one proposed action, JSON arguments and rationale; the core checks the action. Provider failures pause the task without terminating existing experiments. Live provider credentials, tool access and model availability require their own environment checks.

`ljh-research-panel --project-root <project> --open` starts the optional local HTTP adapter. It owns no alternate task store. Other UIs/controllers can replace it using the same protocol. The application docs provide the full request examples and extension contract.

Controller launch is also pluggable: set `settings.controller.command` before task creation. `controller.start` sends the v1 JSON `start` request; the panel has no direct import of the reference module. A custom controller can own its own reasoning implementation. `run.reconcile` requires a direct human decision after uncertain execution has been verified stopped.

## Version and finite task bounds

`setup.version` reads the selection, or changes it with `{"version":"manual"}` / `{"version":"auto"}` through a real human entry. `setup.create` can take the same version. The sole selector is the project convention update_mode. `task.create` freezes research_version, permits up to eight declared evidence_paths, and includes max_task_seconds in authorization (default 3600). The deadline starts on first claim, persists across sessions and is not reset on takeover/resume. New run timeout is capped to remaining authorized task time; expired tasks are fenced on access without requiring a daemon. The reference continuous controller only supports auto. A custom bounded controller can be configured explicitly with controller.supported_versions=["manual"] to launch through controller.start; otherwise manual drivers use individual bounded public operations.

Terminal completed/failed/blocked/cancelled tasks cannot be claimed or revived by old decisions. `task.stop` persists its intent before talking to the executor, invalidates leases and cancels pending decisions. It returns termination_verified and outstanding_run_ids. Only all-terminal execution can finish the stopping state. The executor owns process-tree cancellation and identity checks; this protocol does not confine arbitrary host processes.

## Scientific plan and analysis

`workflow.get` returns packaged guidance: version plus optional topic, or task_id plus optional topic. Version-only guidance can be read before initialization. `research.context(task_id)` returns the selected guide, conclusion rules, two latest decision records, relevant layered-memory results, evidence references/hashes and up to eight relevant card entrypoints. Use recent_records (1..6) or include_evidence=true explicitly when needed; full task history is not loaded by default. Retrieve actual evidence through memory.read or file.read. It is not an exhaustive search.

Use `research.record` with task_id/lease plus one of these payloads. Text below is a structural example, not a scientific conclusion:

```json
{"kind":"plan","record_key":"round-1-plan","question":"Does mechanism H explain observation O?","hypotheses":["H predicts A under intervention I","Alternative/null predicts B under I"],"evidence":["PAPER-ID / EXP-ID / declared log path and relevant observation"],"next_action":"Inspect existing checkpoint or execute a specified comparison","expected_information":"Distinguish A from B","decision_rule":"A: strengthen H; B: revise H; invalid: diagnose reliability","stop_rule":"Question answered or no discriminating action within bounds","run_keys":["round-1-comparison"]}
```

The returned PLAN id is passed as plan_id to run.submit; its request_key must be one of run_keys. Use run_keys=[] when analyzing existing evidence without a new execution. After gathering actual results:

```json
{"kind":"analysis","record_key":"round-1-analysis","plan_id":"PLAN-returned-id","run_ids":["RUN-returned-id"],"observations":"Actual result with source","credibility":"valid","interpretation":"What changed about competing explanations","limitations":"Remaining uncertainty and applicable scope","evidence":["Exact result/log references"],"decision":"stop","next_action":""}
```

credibility is valid/partial/invalid; decision is continue/pivot/stop. Every submitted run for this plan must be included and terminal. Unperformed planned runs require partial/invalid assessment. A new plan requires analysis of the prior plan. A stop analysis prevents new plans, and auto task.complete requires final analysis=stop. task.finish(failed/blocked) can seal work that could not reach scientific analysis. Record keys are idempotent; the same key cannot change content. Scientific records live once in the Markdown task note, not a second database table.

When the reasoning budget is exhausted the reference controller preserves records and seals blocked, rather than invoking the provider again or automatically seeking a fixed budget increment. A valuable out-of-scope continuation can be requested concretely before exhaustion, with cost, expected information and stopping rules, and awaits the user's decision.
