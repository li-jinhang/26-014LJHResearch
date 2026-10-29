# LJH Research application

This repository owns the independent application, protocol and behavioral tests.
The sole global entrypoint is `ljh-research-setup`; its complete distributable
source is the root `ljh-research-setup/` directory. It must work when copied
alone to another machine, without this checkout. Rebuild its bundled wheels
with `tools/build_setup_skill.py` after changing application code or resources.
Setup deploys exactly one selected manual/auto variant into a target project's
`.agents/skills/ljh-research/`; never recreate global research/router skills.
Variant assets live under `src/ljh_research/resources/skill_variants/` and shared
guidance under `src/ljh_research/resources/research/`. Scientific memory is `ljh research docs/`,
separate from skill code. Legacy document trees require explicit setup migration.

Layered-memory callers use the public memory.* operations. Preserve source
attribution, applicability, reading coverage and stale flags; retrieval ranking
is not scientific quality. Legacy dual-root paper layout is explicit compatibility
only. Real-source pilot verification belongs in application .local copies.

Read `CONTEXT.md` and relevant `docs/adr/` decisions. Public clients use
`ljh_research.public` or the version-1 JSON CLI. The controller, local execution
plugin and panel are independent distributions under `packages/`; never import
core storage or service internals from those components.

Use `.venv/Scripts/python.exe` on this Windows checkout. Full behavioral suite:
`python -m unittest discover -s tests -v`. Test providers are deterministic fixtures,
not evidence of model-backed scientific research. Test in temporary workspaces;
do not modify an actual research project as a setup or regression check.

Source migration provenance is in `docs/migration-provenance.json`; pre-migration
working files are preserved in `.local/pre-migration-skill.zip`. Do not replace
them with Git HEAD or overwrite the backup. `.local/` is disposable test/runtime
material and is excluded from source distribution. Retired global skills,
including their Git history and working files, have a durable ZIP under
`archives/`; do not discard that archive as test output.
