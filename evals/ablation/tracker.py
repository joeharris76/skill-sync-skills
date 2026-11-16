"""Call tools on a tractable MCP server over stdio.

Scenario setups use this to seed a throwaway tracker, and checks use it to read
the tracker back, without going through the agent under test.

Usage: tracker.py <repo-root> <cache-dir> '<json list of [tool, arguments]>'
Prints one JSON object per call.
"""

from __future__ import annotations

import json
import subprocess
import sys


def call_tools(repo_root: str, cache_dir: str, calls: list) -> list[dict]:
    proc = subprocess.Popen(
        ["tractable-mcp", "--repo-root", repo_root, "--cache-dir", cache_dir, "--actor", "eval-seed"],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    next_id = 0

    def rpc(method: str, params: dict | None = None, notify: bool = False) -> dict | None:
        nonlocal next_id
        message: dict = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if not notify:
            next_id += 1
            message["id"] = next_id
        proc.stdin.write(json.dumps(message) + "\n")
        proc.stdin.flush()
        if notify:
            return None
        while True:
            reply = json.loads(proc.stdout.readline())
            if reply.get("id") == next_id:
                return reply

    rpc("initialize", {"protocolVersion": "2024-11-05", "capabilities": {},
                       "clientInfo": {"name": "ablation-eval", "version": "1"}})
    rpc("notifications/initialized", {}, notify=True)
    results = []
    for name, arguments in calls:
        reply = rpc("tools/call", {"name": name, "arguments": arguments})
        text = "".join(part.get("text", "") for part in reply.get("result", {}).get("content", []))
        try:
            results.append(json.loads(text))
        except json.JSONDecodeError:
            results.append({"text": text})
    proc.stdin.close()
    proc.terminate()
    return results


if __name__ == "__main__":
    for result in call_tools(sys.argv[1], sys.argv[2], json.loads(sys.argv[3])):
        print(json.dumps(result))
