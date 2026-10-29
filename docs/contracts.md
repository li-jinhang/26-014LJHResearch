# Public contract v1

This is the application boundary, independent of Python configuration storage, skill paths and UI implementation. The public Python entry is `ljh_research.public.dispatch` / `Client`; the mandatory cross-language entry is `python -m ljh_research.cli`. The optional local panel adapter forwards the same requests.

```json
{"protocol_version":1,"request_id":"caller-unique-id","project_root":"/project","method":"task.list","params":{}}
```

```json
{"protocol_version":1,"request_id":"caller-unique-id","ok":true,"result":[]}
```

Errors use `ok:false,error:{code,message,details}`. UTF-8 JSON is the only CLI stdout output. Requests may be provided on stdin or as `method --project-root ... --params @file.json`. Reject unknown protocol versions. Caller-supplied JSON cannot set a human principal.

## Operations

| Group | Operations |
| --- | --- |
| Setup | `system.capabilities`, `setup.plan/create/validate/repair/version/deploy/migrate`, `workflow.get` |
| Defaults / driver plugins | `workspace.get`, `config.update`, `settings.get/update`, `controller.start` |
| Task lifecycle | `task.create/get/list/claim/heartbeat/pause/cancel/complete/finish/stop/revoke` |
| Decisions | `decision.request/list/resolve` |
| Execution | `run.submit/refresh/list/logs/cancel/reconcile` |
| Research | `file.read/write`, `evidence.record`, `knowledge.invoke`, `research.context/record`, `memory.import/extract/search/read/rebuild/status` |
| Reasoning/observation | `reasoning.reserve/record`, `event.list` |

Setup create/repair/deploy/migrate, changes to defaults/bindings, resolving decisions, explicit takeover, revocation and manual run cancellation/reconciliation need a human entry and concrete evidence. In a coding-agent workflow, `--human --evidence <actual-user-confirmation>` conveys the user's decision. The reference controller never uses that entry. This is a trusted local principal distinction and auditable protocol, not cryptographic proof of who typed a shell command.

## Task authorization and ownership

`task.create` takes title/objective/stop_condition, optional evidence_paths (up to eight declared text sources), and an authorization object containing project-relative `allowed_roots`, explicit `allowed_programs`, `max_runs`, `max_reasoning_calls`, `max_run_seconds`, `max_task_seconds` (default 3600). It returns a task and pending authorization decision. Defaults/bindings and research_version are snapshotted. `setup.version` selects manual/auto for new tasks using the existing project convention update_mode; there is no duplicate mode switch in settings.

After approval, `task.claim(task_id,driver_id)` returns a private lease. Renew via `task.heartbeat` within five minutes. Another driver cannot claim it without explicit human takeover; takeover increments the ownership epoch and invalidates the old token. A driver timeout does not cancel running experiments. Claiming another task is blocked while a task is active or a prior task has unfinished runs.

Authorization persists until revoked/cancelled or the applicable budget is exhausted. A lease is not an authorization. Approved `budget_extension` requests can increase the specified counters; they never reset usage. A completed task cannot be reopened by a driver.

`task.pause` stops new scheduling and releases ownership. `task.cancel` revokes scheduling authority but preserves runs. `run.cancel` separately asks the executor to stop that run. `run.reconcile` closes uncertain execution only after a human has verified it stopped, preserving evidence and budget; it cannot invent a successful run.

`task.stop` is the irreversible termination operation: persist stopping, revoke ownership, cancel pending decisions, request cancellation of every unfinished task run and verify actual terminal states. It accepts a direct user request or the valid owner's scoped termination action. stopping/unknown is not success; return outstanding_run_ids and termination_verified. Finalize cancelled/failed/blocked only when all runs are terminal; late submit acknowledgments also see the stop intent and are cancelled. `task.finish` seals completed/failed/blocked work with summary only after all runs are terminal. Terminal tasks cannot be claimed or reactivated by old decisions. The total deadline begins on first claim and survives resumption; process timeouts are capped by its remaining time. With no daemon, expired scheduling is closed on subsequent task access.

## Manual and automatic scientific workflows

Manual completes the user-selected deliverable and ends; it does not automatically launch another optimization round. Auto compares hypotheses, chooses informative actions, runs and analyzes results, and decides continue/pivot/stop. Both share packaged guidance through `workflow.get`; the exact record field contract is in `workflow.get(topic=task-control)`. An explicit version allows reading guides even before workspace initialization.

`research.record` appends idempotent plan/analysis records to the Markdown task note. Auto run.submit requires a current plan_id and declared request_key; new plans require analysis of the prior one; analysis accounts for all associated terminal runs. Unperformed planned runs cannot produce a valid assessment. Completion requires final analysis=stop; failure/blockage may use task.finish without inventing scientific analysis. `research.context` recovers the last six records, bounded source excerpts/hashes, note tail and card entrypoints with explicit omission flags. Excerpts are not an exhaustive scientific audit. This validates workflow structure, not the truth or quality of a hypothesis or analysis.

## Files, scientific memory and state

Project conventions are stored once in `01约束文件.md`. Configuration queries and changes are business operations, not raw frontmatter editing by the UI. Reads require declared roots; generic writes require authorized roots, exclude workspace internals and require the prior SHA256 when replacing existing content.

Scientific evidence and qualified final conclusions are Markdown task notes/cards. Task completion saves a result-note reference in the ledger; returned summary text is a projection from that note. Runtime coordination uses a versioned SQLite database with transactions. Recent reasoning observations are bounded diagnostic context, not a second scientific authority.

Initialization/repair prepares the task store. Daily service operations do not create a missing workspace or missing task runtime. The compatibility research CLI retains migrated card and paper behavior; use `knowledge.invoke` for task-mediated operations. The low-level compatibility modules are trusted maintenance interfaces, not a sandbox boundary.

## Execution plugin protocol

Plugins are executable argv arrays, not shell command strings. One UTF-8 request on stdin yields one UTF-8 response on stdout:

```json
{"protocol_version":1,"request_id":"id","method":"status","params":{"project_root":"/project","run_id":"RUN-example"}}
```

```json
{"protocol_version":1,"request_id":"id","ok":true,"result":{"status":"running"}}
```

Required operations: `submit`, `status`, `logs`, `cancel`; `capabilities` reports supported behavior. `submit` receives a stable run_id, argv, absolute plugin-side cwd and timeout_seconds. The local plugin is a reference implementation. Remote plugins own connection details, path mapping, process identities and recovery. No SSH code or remote pathname assumptions belong in scientific logic.

The core reserves run identity and budget before submission. A submission timeout is uncertain, not permission to retry under a new identity. Identical request_key+argv+cwd+timeout returns the existing run. Changing submission contents under the same key is rejected. Detached local workers keep output/status files and report process birth identity to reduce PID-reuse errors. Status refresh never launches work or consumes budget.

## Reasoning plugin protocol

Generic command providers receive `{protocol_version,instructions,context,schema}`. They return:

```json
{"action":"file.write","arguments":"{\"path\":\"runs/study/main.py\",\"content\":\"...\"}","rationale":"Mechanism and evidence motivating this next step"}
```

Allowed actions are file.read/write, run.submit, evidence.record, knowledge.invoke, decision.request, task.complete/pause/finish/stop, workflow.get and research.record. Providers cannot supply lease/task_id/human credentials or grant budgets. Controller ownership and scope are appended by the driver and checked by core. Model output and tool logs are untrusted proposals/evidence.

The controller reconstructs context from persisted task/run/decision records, research.context and bounded recent observations. It reconciles active runs before asking for another action, keeps ownership alive during reasoning, and pauses with an error if the provider fails. Exhausted reasoning budget preserves partial evidence and seals blocked without another call or automatic budget-extension request. Generic providers may be written in any language. `examples/demo_reasoning.py` is explicitly a deterministic fixture.

## HTTP adapter and UI

The optional adapter binds to loopback with an ephemeral port and one selected project. `/api/bootstrap` provides the local session token; `/api/operation` accepts business requests using `X-LJH-Token` and same-origin checks. The project binding cannot be overridden by request JSON. `/api/controller/start` calls the task-snapshotted controller plugin only for an authorized queued/paused task. The panel does not import a particular controller implementation.

The frontend ships as standalone HTML/CSS/JS assets. It depends on neither the Markdown layout nor internal Python modules. Its views, task form, decision controls, environment forms and activity feed can be replaced without changing the task ledger or scientific operations. The adapter is for the local trusted-user workstation; a remote multi-user service requires an independently designed authentication/deployment adapter.

## Controller launcher plugin

A controller binding is an argv array in `settings.controller.command`, snapshotted at task creation. `controller.start` sends a v1 JSON plugin request with `method=start` and `params={project_root,task_id}`. The plugin acknowledges with the matching request_id and its own driver launch metadata. The reference controller implements this protocol and stores its logs in user-level application state, without reading the core task database or relying on its internal directory layout. A JavaScript controller fixture validates that the configured foreign-language implementation is actually called.

Controller bindings may declare supported_versions=["manual","auto"]. The default and reference controller support auto only. A custom bounded manual controller must be explicitly configured as supporting manual before task creation; this changes neither authorization nor termination semantics.

## Project-local skill deployment

The sole global research entry is ljh-research-setup. Variant assets are bundled in the core, outside global discovery. setup.create deploys the selected variant into <project>/.agents/skills/ljh-research/ and creates <project>/ljh research docs/. setup.deploy installs/updates the local entry in an owned workspace; setup.version with version=manual/auto synchronizes that same slot with the project's selector. The public skill name is ljh-research. workspace.get and setup.validate project skill_deployment status. A deployment marker records managed file hashes; edited or unmanaged files are conflicts, not permission to overwrite. Existing task snapshots retain their research version.

The project-local launcher binds to its installation project from any cwd and rejects foreign --project-root or JSON project_root values. Core, executor, controller and guidance remain independent of the skill path. tools/install_skills.py refreshes global setup only; it must not recreate global research variants or the former router.

setup.plan refuses parallel document trees when legacy .ljh-research/ or ljh research/ exists. setup.migrate (optional source equal to one recognized legacy name) requires explicit user evidence, one owned legacy tree, an absent destination and idle/reconciled execution. It renames to ljh research docs, updates path references in Markdown/JSON/task records, preserves resource counters and backs up changed metadata. Historical events retain original paths. A migration lock blocks new ledger operations; inspect an interrupted lock rather than automatically deleting it. Unsupported legacy formats and conflicting local skills remain untouched for review.

## Layered memory contract

memory.import registers a stable paper/experiment/research_point/reproduction/experience from a project-relative source. Paper originals and extracted full text use flat type roots; topics are many-to-many metadata/views. Optional reading_notes attach existing notes; reimporting the same original with additional notes extends it without copying the original again. Automatic extraction produces conservative source excerpts, classified as paper_claim/reading_note/project_record; it does not certify scientific validity. Card creation/conclusion through knowledge.invoke captures the existing card by reference, and the default experience command writes individual records under 5经验.

memory.extract(id) refreshes structural excerpts; explicit claims carry text, aspect, conditions, keywords, evidence_type and citations(source_id,source_sha256,start_line,end_line,quote). Exact quoted evidence and current hashes are required. Agent semantic writeback merges existing valid points; supersedes lists explicitly replaced points. Previous revisions are retained. A changed PDF must be registered as a new original version, while refresh_text retries extraction from an unchanged original. Reading coverage is partial; source freshness is separate from credibility. Topic/source changes never silently promote evidence to scientifically validated.

memory.search(query,purpose,budget_chars,kind?,topic?,limit?) ranks lexical relevance over registered knowledge and aliases. purpose is overview/innovation/experiment_design/result_analysis/debug/reproduction. Whole JSON results respect budget_chars (Unicode characters, 600..50000); complete knowledge points are omitted rather than cutting qualifications. Results expose conditions, source nature, freshness and drill-down IDs. Zero hits do not prove no previous research. Index/topic views are derived; deleting the index does not delete knowledge.

memory.read(id) returns a bounded object summary. topic plus optional kind reads a topic view. view=detail with source_id returns an outline; exact section or start_line/end_line selects evidence, with hash and line references. Stale topic views return routing instead of their old body. memory.status exposes pending extraction, source invalidation and pending views. memory.rebuild rebuilds views while preserving unmanaged user content as a visible conflict.

The caller needs a real human entry or valid task ownership for import/extract/rebuild; task imports read only declared roots. Pure search/read/status do not grant authority to mutate. Markdown records remain the knowledge authority; .runtime/memory/index.json is disposable. Use workflow.get(topic=layered-memory) for the skill reading/writeback discipline.

research.context now defaults to two recent scientific records, relevant memory retrieval, source references/hashes and up to eight lexically related cards. include_evidence=true explicitly opts into the legacy 4000-character source excerpts; recent_records can be 1..6. Full task history and the workspace-wide card catalog are not passed by default by the reference controller. These are component budgets, not a token ceiling for an entire coding-agent conversation.
