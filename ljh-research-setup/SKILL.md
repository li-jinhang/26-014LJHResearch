---
name: ljh-research-setup
description: 'Install the bundled LJH Research runtime, initialize a project, and deploy or switch its manual/auto research skill. Use for environment preparation, project deployment, configuration and explicit legacy migration; scientific work uses the deployed project-local ljh-research.'
---

# LJH Research Setup

This directory is the complete portable setup skill. It includes the core, local executor, reference controller, panel, both research variants and shared guidance in `assets/wheels/`. Copy or install this whole directory; no application checkout or developer-machine path is required. Only setup is global. Each selected project receives one `ljh-research` skill, with scientific memory separately in `ljh research docs/`.

## Prepare the runtime

Inspect the user's environment and existing deployment. Reuse a working Python >= 3.11 and an isolated tool environment. Read [bootstrap.md](references/bootstrap.md) for platform-specific preparation, including machines without Python.

Run the native bootstrap script from this skill's own directory. Its default is a read-only plan; installation requires `-Apply` / `--apply`. The bundled wheels install offline by default. Show concrete destinations and changes before installation unless already authorized. Do not use a training environment or change global PATH. The user runtime binding records the installed interpreter, not the source checkout or skill location.

```powershell
& '<this-skill>/scripts/bootstrap.ps1' -Python '<python.exe>'
& '<this-skill>/scripts/bootstrap.ps1' -Python '<python.exe>' -Apply
```

```sh
sh '<this-skill>/scripts/bootstrap.sh' --python '/path/to/python3'
sh '<this-skill>/scripts/bootstrap.sh' --python '/path/to/python3' --apply
```

The optional PDF dependency is installed only when `-Papers` / `--papers` is requested; it needs a package index. Provider credentials remain with the provider. Never store raw API keys in workspace settings.

## Deploy to the selected project

Use `python <this-skill>/scripts/setup.py` with the following operations. The launcher selects an installed runtime; it never imports application source from this directory's parent.

```text
python <this-skill>/scripts/setup.py doctor
python <this-skill>/scripts/setup.py plan --project-root <project> --version manual
python <this-skill>/scripts/setup.py create --project-root <project> --version manual --approve
python <this-skill>/scripts/setup.py version --project-root <project>
python <this-skill>/scripts/setup.py version --project-root <project> --select auto --approve
python <this-skill>/scripts/setup.py deploy --project-root <project> --version manual --approve
python <this-skill>/scripts/setup.py validate --project-root <project>
python <this-skill>/scripts/setup.py repair --project-root <project> --approve
```

Establish the version from the user's instruction or an existing selection. For a new workspace with no choice, explain and ask: manual completes bounded user-selected work and ends; auto retrieves evidence, compares hypotheses, selects informative experiments and decides continue/pivot/stop within task authorization. The API's manual default is not evidence that the user selected a version. Read-only inspection can continue while waiting.

`--approve` conveys actual user authorization for the concrete changes. `create` initializes documents and deploys the selected local skill together. `deploy` updates it; `repair` fills missing owned structure. Preserve edited or unmanaged files and report conflicts. Setup targets only the named project. The project root is not the document directory itself.

Version selection updates `01约束文件.md`'s `update_mode` (manual -> manual, auto -> automatic) and the deployed skill. Existing tasks retain their frozen version, bindings and authorization. Switching backs up replaced managed files and preserves unrelated files. After setup, read `<project>/.agents/skills/ljh-research/SKILL.md` and hand scientific work to it. For settings and adapter bindings, read [configuration.md](references/configuration.md).

## Existing documents and validation

An existing `ljh research/` or `.ljh-research/` requires explicit migration after inspection:

```text
python <this-skill>/scripts/setup.py migrate --project-root <project> --from "ljh research" --approve
```

Migration requires one supported owned legacy tree, no active or unreconciled runs, and an absent destination. It preserves scientific records and budgets, updates recorded paths, and backs up changed metadata. Report ownership or destination conflicts without merging or overwriting. Implementation checks use temporary workspaces, not actual research projects.

Verify imports, CLI JSON, workspace validation and executable capabilities. A configured provider is not verified until actually tested; setup checks do not require training or live model calls. Report platform and provider verification limits. The local executor runs trusted host processes; stronger isolation belongs in a dedicated execution plugin.
