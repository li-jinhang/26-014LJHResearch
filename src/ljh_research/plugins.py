"""Language-neutral JSON subprocess plugin transport."""
import json
import os
import subprocess
import uuid
from .errors import ResearchError, require


def call(command, method, params, timeout=30):
    require(isinstance(command, list) and command and all(isinstance(x, str) for x in command),
            "invalid_plugin", "Plugin command must be a nonempty argv array")
    request_id = uuid.uuid4().hex
    request = {"protocol_version": 1, "request_id": request_id, "method": method, "params": params}
    try:
        result = subprocess.run(command, input=json.dumps(request, ensure_ascii=False), capture_output=True,
                                encoding="utf-8", timeout=timeout, check=False, env={**os.environ, "PYTHONUTF8": "1"})
        payload = json.loads(result.stdout)
    except (OSError, subprocess.TimeoutExpired, json.JSONDecodeError) as exc:
        raise ResearchError("plugin_unavailable", str(exc), {"method": method}) from exc
    require(result.returncode == 0 and payload.get("ok") is True,
            "plugin_error", str(payload.get("error", result.stderr[-2000:])))
    require(payload.get("protocol_version") == 1 and payload.get("request_id") == request_id,
            "plugin_protocol", "Plugin response does not match request")
    return payload["result"]
