# Configuration contract

Research version is selected via `setup.version` and projected as `workspace.get.research_version` / `skill_name`. Its sole persisted source is project convention `update_mode` (`manual` -> manual, `automatic` -> auto). Task creation freezes the version and includes it in the authorization payload. Existing unversioned tasks retain manual semantics. Never infer automatic execution authorization from this default.

`skill_name` is always `ljh-research`, deployed only at `<project>/.agents/skills/ljh-research/`. `create`, `deploy` and selected `version` operations install one variant from packaged resources. `workspace.get.skill_deployment` / `setup.validate` report the deployment status. Its marker tracks managed file hashes; edited or unmanaged content is preserved as a conflict. No auto/manual global skill is installed. Scientific records are in `<project>/ljh research docs/`; legacy names require an explicit idle-only `setup.migrate`.

Project paths are relative to the selected project root. Reject `..`, absolute paths and symlink escapes. Declare only known facts. User/machine-level executable paths belong in environment bindings, not scientific project-path fields.

The public API supports:

```json
{"protocol_version":1,"method":"settings.update","project_root":"<project>","params":{"reasoning":{"kind":"codex","command":["<verified-codex-executable>"],"timeout_seconds":120},"executor":{"command":["<tool-python>","-m","ljh_research_local"]}}}
```

`settings.update` requires direct user confirmation. For a generic reasoning plugin, use `kind=command`; it consumes a JSON request on stdin and returns an action proposal on stdout. Codex and Claude adapters are convenience providers. Their credentials remain with the provider; do not copy them into the workspace.

Set bindings before creating a task: task snapshots intentionally preserve their original bindings. To change a task's environment, pause and create a reviewed replacement task; do not edit its ledger by hand.

Core interfaces use argv arrays, never interpolated shell command strings. Executable verification should reject broken shims even when they exit with code zero. Native application paths may change during updates; configure and revalidate them rather than embedding version hashes in the core.

The local executor is a trusted host-process adapter, not an operating-system sandbox. Core authorization validates submitted paths/programs and budgets; arbitrary local processes or agents running outside the API are not technically confined by that validation. Strong isolation belongs in a dedicated execution plugin.

Use `controller:{command:[...]}` in settings to choose the module launched by the panel. It uses the JSON plugin `start` request and is independent of the reasoning and execution bindings. All three bindings are snapshotted into new tasks.

The reference continuous controller supports auto only. A custom controller that implements manual's bounded execution and termination contract may declare `supported_versions:["manual"]` (or both versions) in its controller binding before task creation. The core enforces the task's snapshotted support declaration; the module remains responsible for selecting actions consistent with the version. Language and UI remain independent of this choice.
