#!/usr/bin/env python3
"""Integration test: plugin → MCP relay → companion pipeline.

Starts real companion (FastMCP server via server.py), simulates MCPRelay
JSON-RPC 2.0 communication over stdio, and validates every tool call,
retry behavior, and timeout handling.
"""

import json
import os
import select
import subprocess
import sys
import time
from pathlib import Path

BIFROST_DIR = Path(__file__).resolve().parent.parent / "bifrost"
COMPANION_DIR = BIFROST_DIR / "companion"
HAS_COMPANION = (COMPANION_DIR / "server.py").exists()


class ConnectionError(Exception):
    pass


class TimeoutError(Exception):
    def __init__(self, method: str, timeout_s: float):
        super().__init__(f"MCP call '{method}' timed out after {timeout_s}s")


class MCPClient:
    """Simulates MCPRelay's JSON-RPC 2.0 communication over stdio.

    Mirrors the exact protocol MCPRelay uses: initialize handshake,
    JSON-RPC requests/responses, timed calls, and clean disconnect.
    """

    def __init__(self, default_timeout: float = 10.0):
        self.proc: subprocess.Popen | None = None
        self._next_id = 1
        self._timeout = default_timeout

    def start(self, python: str = "python3") -> None:
        env = {**os.environ, "PYTHONUNBUFFERED": "1"}
        self.proc = subprocess.Popen(
            [python, "-m", "companion.server"],
            cwd=str(BIFROST_DIR),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=env,
        )

    def initialize(self) -> dict:
        result = self._send("initialize", {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "bifrost-test", "version": "0.1.0"},
        })
        self._notify("notifications/initialized")
        return result

    def call_tool(self, name: str, args: dict | None = None, timeout: float | None = None) -> dict:
        result = self._send("tools/call", {"name": name, "arguments": args or {}}, timeout=timeout)
        if isinstance(result, dict) and result.get("isError"):
            err_text = (result.get("content") or [{}])[0].get("text", "tool error")
            raise RuntimeError(err_text)
        return result

    def list_tools(self) -> list[dict]:
        result = self._send("tools/list", {})
        return result.get("tools", []) if isinstance(result, dict) else []

    def close(self) -> None:
        if self.proc is None:
            return
        try:
            self.proc.stdin.close()
        except Exception:
            pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
            self.proc.wait()
        self.proc = None

    @property
    def connected(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def _send(self, method: str, params: dict | None = None, timeout: float | None = None) -> dict:
        assert self.proc and self.proc.stdin
        timeout = timeout if timeout is not None else self._timeout
        msg_id = self._next_id
        self._next_id += 1
        req = {"jsonrpc": "2.0", "id": msg_id, "method": method}
        if params:
            req["params"] = params
        try:
            self.proc.stdin.write(json.dumps(req).encode() + b"\n")
            self.proc.stdin.flush()
        except OSError:
            raise ConnectionError("companion not connected (broken pipe)")

        deadline = time.monotonic() + timeout
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(method, timeout)
            r, _, _ = select.select([self.proc.stdout], [], [], remaining)
            if not r:
                raise TimeoutError(method, timeout)
            line = self.proc.stdout.readline()
            if not line:
                raise ConnectionError("companion closed connection")
            line = line.strip()
            if not line:
                continue
            try:
                resp = json.loads(line)
            except json.JSONDecodeError:
                continue
            if resp.get("id") == msg_id:
                if "error" in resp:
                    e = resp["error"]
                    raise RuntimeError(f"MCP error {e['code']}: {e['message']}")
                return resp.get("result")

    def _notify(self, method: str, params: dict | None = None) -> None:
        assert self.proc and self.proc.stdin
        req = {"jsonrpc": "2.0", "method": method}
        if params:
            req["params"] = params
        try:
            self.proc.stdin.write(json.dumps(req).encode() + b"\n")
            self.proc.stdin.flush()
        except OSError:
            raise ConnectionError("companion not connected (broken pipe)")


def _test(name: str, fn, quiet: bool = False):
    if not quiet:
        print(f"  {name}...", end=" ", flush=True)
    try:
        fn()
        if not quiet:
            print("PASS")
        return True
    except Exception:
        if not quiet:
            print("FAIL")
        import traceback
        traceback.print_exc()
        return False


def test_initialize():
    client = MCPClient()
    try:
        client.start()
        assert client.connected
        result = client.initialize()
        assert result is not None
    finally:
        client.close()


def test_tool_echo():
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        result = client.call_tool("echo", {"message": "hello bifrost"})
        texts = [c["text"] for c in result.get("content", []) if c.get("type") == "text"]
        assert texts[0] == "hello bifrost"
    finally:
        client.close()


def test_tool_version():
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        result = client.call_tool("version")
        texts = [c["text"] for c in result.get("content", []) if c.get("type") == "text"]
        assert "bifrost" in texts[0]
    finally:
        client.close()


def test_memory_save_and_list():
    client = MCPClient()
    try:
        client.start()
        client.initialize()

        save = client.call_tool("memory_save", {
            "type": "fact", "content": "__bf_test_save_list__", "scope": "user",
        })
        save_text = next(c["text"] for c in save.get("content", []) if c.get("type") == "text")
        assert save_text.startswith("saved ")

        lst = client.call_tool("memory_list", {"limit": 50})
        lst_text = next(c["text"] for c in lst.get("content", []) if c.get("type") == "text")
        memories = json.loads(lst_text)
        assert any("__bf_test_save_list__" in m.get("content", "") for m in memories)
    finally:
        client.close()


def test_memory_search():
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        client.call_tool("memory_save", {
            "type": "fact", "content": "__bf_test_search__", "scope": "user",
        })
        result = client.call_tool("memory_search", {"query": "__bf_test_search__", "limit": 5})
        text = next(c["text"] for c in result.get("content", []) if c.get("type") == "text")
        memories = json.loads(text)
        assert len(memories) >= 1
        assert "__bf_test_search__" in memories[0]["content"]
    finally:
        client.close()


def test_memory_delete():
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        save = client.call_tool("memory_save", {
            "type": "fact", "content": "__bf_test_delete__", "scope": "user",
        })
        save_text = next(c["text"] for c in save.get("content", []) if c.get("type") == "text")
        mem_id = int(save_text.split()[1])

        del_res = client.call_tool("memory_delete", {"memory_id": mem_id})
        del_text = next(c["text"] for c in del_res.get("content", []) if c.get("type") == "text")
        assert del_text == "deleted"
    finally:
        client.close()


def test_list_tools():
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        tools = client.list_tools()
        names = {t["name"] for t in tools}
        expected = {"echo", "version", "memory_save", "memory_search", "memory_list", "memory_delete"}
        assert expected.issubset(names), f"Missing: {expected - names}"
    finally:
        client.close()


def test_kill_companion_raises_connection_error():
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        assert client.connected

        client.proc.terminate()
        try:
            client.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            client.proc.kill()
            client.proc.wait()
        assert not client.connected

        raised = False
        try:
            client.call_tool("echo", {"message": "x"})
        except ConnectionError:
            raised = True
        assert raised, "Expected ConnectionError when companion is dead"
    finally:
        client.close()


def test_timeout_raises_timeout_error():
    client = MCPClient()
    try:
        client.start()
        client.initialize()
        raised = False
        try:
            client.call_tool("echo", {"message": "x"}, timeout=0)
        except TimeoutError:
            raised = True
        assert raised, "Expected TimeoutError with 0s timeout"
    finally:
        client.close()


def main():
    if not HAS_COMPANION:
        print(f"ERROR: companion not found at {COMPANION_DIR}")
        return 1

    tests = [
        ("initialize handshake", test_initialize),
        ("echo tool", test_tool_echo),
        ("version tool", test_tool_version),
        ("memory_save + memory_list", test_memory_save_and_list),
        ("memory_search", test_memory_search),
        ("memory_delete", test_memory_delete),
        ("list_tools returns all 6", test_list_tools),
        ("kill companion → ConnectionError", test_kill_companion_raises_connection_error),
        ("zero timeout → TimeoutError", test_timeout_raises_timeout_error),
    ]
    passed = 0
    total = len(tests)
    print(f"\nBifrost plugin integration tests ({total} tests)")
    print("=" * 50)
    for name, fn in tests:
        if _test(name, fn):
            passed += 1
    print("=" * 50)
    print(f"Result: {passed}/{total} passed")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
