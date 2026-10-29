"""Small, shared Windows-safe console setup for every command-line entry point."""

from __future__ import annotations

import sys


def configure_utf8() -> None:
    """Prefer UTF-8 for help, errors, and normal output when streams allow it.

    ``TextIOWrapper.reconfigure`` is available on the Python versions supported by
    this skill.  The guard keeps the helper safe for redirected or test streams
    that deliberately do not expose it.
    """

    for stream in (sys.stdout, sys.stderr):
        reconfigure = getattr(stream, "reconfigure", None)
        if callable(reconfigure):
            reconfigure(encoding="utf-8", errors="backslashreplace")
