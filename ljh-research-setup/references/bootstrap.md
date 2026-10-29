# Portable runtime bootstrap

Install or copy this complete `ljh-research-setup/` directory into your agent's global skills directory. A GitHub checkout is only needed by maintainers to rebuild the bundle. The release includes four pure-Python wheels and a SHA256 manifest in `assets/wheels/`; these contain both research variants, templates, shared guidance and the panel's web assets.

## Windows

Run `scripts/bootstrap.ps1` from any working directory. `-Python <python.exe>` selects an existing Python >= 3.11. Without `-Apply`, it only validates the bundle and displays the plan. With `-Apply`, it creates `%LOCALAPPDATA%/LJHResearch/venv`, installs the bundled wheels without a package index, verifies imports, and atomically registers `%LOCALAPPDATA%/LJHResearch/runtime.json`. `-RuntimeDirectory <path>` selects a different user-owned destination.

If Python is missing, verify a supported release on the official Python download page and supply `-InstallerUrl <https://www.python.org/...exe>`. The bootstrap verifies the HTTPS host and Python Software Foundation Authenticode signature. `-InstallerSha256 <trusted-checksum>` adds a checksum check. It installs into the selected runtime directory without changing PATH. Review this concrete installation plan before applying it.

## Linux

Run `sh scripts/bootstrap.sh --python /path/to/python3` and add `--apply` for the reviewed installation. `--runtime-dir <path>` overrides `${XDG_DATA_HOME:-$HOME/.local/share}/ljh-research`. The binding is `${XDG_CONFIG_HOME:-$HOME/.config}/ljh-research/runtime.json`.

Without Python, provide `--runtime-url` and `--runtime-sha256` for a verified official `astral-sh/python-build-standalone` GitHub release matching the OS/architecture. Bootstrap checks the host, checksum and archive paths and extracts into a fresh user-owned location. It requires curl, tar and sha256sum, and does not request sudo. If a system Python lacks venv/ensurepip, report the missing capability or use the standalone runtime route.

## Dependencies and recovery

The default installation needs a working Python/venv/pip but no network or build tools. Optional `-Papers` / `--papers` fetches PDF support from a package index; live model providers are configured and verified separately. Missing-Python downloads also need network access. A failed installation leaves the previous runtime binding unchanged, though an existing runtime environment may have been updated; inspect the error before reapplying.

Launchers use the current interpreter if it has the installed core, otherwise the registered interpreter. The installed runtime contains all scientific rules and templates; keeping the source checkout or setup download is unnecessary for existing deployments. Keep a setup copy to deploy, switch or repair projects later.

`LJH_RESEARCH_RUNTIME_BINDING=<absolute-json-path>` selects an alternate binding for isolated environments and tests. Bootstrap and launchers both honor it. The binding contains machine-specific interpreter configuration; distribute the setup directory, not your runtime or binding.

Verify `scripts/setup.py doctor`, then create and validate a temporary project. Report which platform and provider capabilities were actually exercised; an import check does not demonstrate scientific reasoning quality.
