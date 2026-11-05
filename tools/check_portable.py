"""Проверить распакованный ZIP с его собственным Python из другого каталога."""

import argparse
import json
import os
from pathlib import Path
import subprocess
import tempfile


def check(package, pob_dir):
    python = package.resolve() / "python/python.exe"
    requests = [
        {"id": 1, "method": "initialize", "params": {"protocolVersion": "2025-11-25"}},
        {"id": 2, "method": "tools/list"},
        {"id": 3, "method": "tools/call", "params": {"name": "pob_create_build", "arguments": {"name": "Portable test", "level": 42}}},
        {"id": 4, "method": "tools/call", "params": {"name": "pob_add_item", "arguments": {"raw": "Rarity: Normal\nWithered Wand\n", "slot": "Weapon 1"}}},
        {"id": 5, "method": "tools/call", "params": {"name": "pob_check_build", "arguments": {"targets": [{"stat": "Life", "min": 1}]}}},
        {"id": 6, "method": "tools/call", "params": {"name": "pob_export_xml", "arguments": {}}},
    ]
    args = [str(python), "-X", "utf8", "-m", "pob_poe2_mcp"]
    with tempfile.TemporaryDirectory() as temporary:
        config = subprocess.run(args + ["config"], cwd=temporary, capture_output=True, encoding="utf-8", check=True)
        assert set(json.loads(config.stdout)["mcpServers"]) == {"pob-engine", "pob-app"}
        env = {**os.environ, "PATH": os.environ.get("SystemRoot", "C:/Windows") + "/System32"}
        process = subprocess.run(
            args + ["serve", "--pob-dir", str(pob_dir.resolve())],
            cwd=temporary, env=env,
            input="\n".join(json.dumps({"jsonrpc": "2.0", **request}) for request in requests) + "\n",
            capture_output=True, encoding="utf-8", timeout=90, check=True,
        )
    responses = [json.loads(line) for line in process.stdout.splitlines()]
    assert len(responses) == len(requests), process.stderr
    assert len(responses[1]["result"]["tools"]) == 13
    for response in responses:
        assert "error" not in response, response
        assert not response["result"].get("isError"), response
    assert responses[4]["result"]["structuredContent"]["result"]["targetsPassed"]
    assert "<PathOfBuilding2>" in responses[5]["result"]["structuredContent"]["result"]["xml"]
    print("PORTABLE_OK: свой Python, другой каталог, без Python/Git в PATH, 13 инструментов, предмет, отчёт, XML")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("package", type=Path)
    parser.add_argument("--pob-dir", type=Path, required=True)
    args = parser.parse_args()
    check(args.package, args.pob_dir)
