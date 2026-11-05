"""Собрать ZIP с официальным встроенным CPython без pip и сторонних пакетов."""

import argparse
import hashlib
import json
from pathlib import Path
import shutil
import tempfile
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]
PYTHON_URL = "https://www.python.org/ftp/python/3.14.10/python-3.14.10-embed-amd64.zip"
PYTHON_SHA256 = "90905e64a840557d8c1bc4f5b74db3d7ee85e3ffb217611cac1c7813acea4159"


def build(output):
    output.mkdir(parents=True, exist_ok=True)
    runtime_zip = output / "python-3.14.10-embed-amd64.zip"
    if not runtime_zip.exists():
        with urllib.request.urlopen(PYTHON_URL, timeout=60) as response:
            runtime_zip.write_bytes(response.read())
    if hashlib.sha256(runtime_zip.read_bytes()).hexdigest() != PYTHON_SHA256:
        raise ValueError("SHA-256 архива Python не совпал с опубликованным python.org")
    with tempfile.TemporaryDirectory(prefix="pob-portable-") as temporary:
        package = Path(temporary) / "pob-poe2-mcp"
        runtime = package / "python"
        runtime.mkdir(parents=True)
        with zipfile.ZipFile(runtime_zip) as archive:
            archive.extractall(runtime)
        (runtime / "python314._pth").write_text("python314.zip\n.\n..\n", encoding="utf-8")
        shutil.copytree(ROOT / "pob_poe2_mcp", package / "pob_poe2_mcp", ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        for name in ["README.md", "CHANGELOG.md", "LICENSE"]:
            shutil.copy2(ROOT / name, package / name)
        shutil.copytree(ROOT / "licenses", package / "licenses")
        (package / "pob-mcp.cmd").write_text('@echo off\r\n"%~dp0python\\python.exe" -X utf8 -m pob_poe2_mcp %*\r\n', encoding="ascii", newline="")
        for name, command in [("check", "doctor"), ("connect-app", "install-bridge"), ("disconnect-app", "uninstall-bridge"), ("mcp-config", "config")]:
            text = f'@echo off\r\ncall "%~dp0pob-mcp.cmd" {command} %*\r\npause\r\n'
            (package / f"{name}.cmd").write_text(text, encoding="ascii", newline="")
        config = {"mcpServers": {
            "pob-engine": {"command": "C:/Tools/pob-poe2-mcp/python/python.exe", "args": ["-X", "utf8", "-m", "pob_poe2_mcp", "serve", "--mode", "engine"]},
            "pob-app": {"command": "C:/Tools/pob-poe2-mcp/python/python.exe", "args": ["-X", "utf8", "-m", "pob_poe2_mcp", "serve", "--mode", "app"]},
        }}
        (package / "mcp-config.example.json").write_text(json.dumps(config, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        target = output / "pob-poe2-mcp-windows-x64.zip"
        with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
            for path in sorted(package.rglob("*")):
                if path.is_file():
                    archive.write(path, path.relative_to(package.parent))
    return target


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    print(build(parser.parse_args().output))
