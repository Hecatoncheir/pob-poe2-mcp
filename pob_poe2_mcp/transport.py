"""Транспорт к отдельному движку или к Lua-мосту открытого приложения."""

import json
import os
from pathlib import Path
import socket
import subprocess
import sys

from .errors import EngineError


def bridge_state_dir():
    return Path(os.environ.get("LOCALAPPDATA", Path.home() / ".local/share")) / "pob-poe2-mcp/bridge"


class ProcessTransport:
    token = None

    def __init__(self, pob_dir):
        runner = Path(__file__).with_name("runner.py")
        self.process = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(runner), "--pob-dir", str(pob_dir)],
            cwd=pob_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=sys.stderr, text=True, encoding="utf-8", bufsize=1,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        self.reader = self.process.stdout

    def send(self, line):
        if self.process.poll() is not None:
            raise EngineError("ENGINE_STOPPED", "Процесс Lua завершился; перезапустите клиент")
        self.process.stdin.write(line)
        self.process.stdin.flush()

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        for stream in [self.process.stdin, self.process.stdout]:
            if stream:
                stream.close()


class AppTransport:
    def __init__(self, pob_dir=None, endpoint=None):
        endpoint_path = Path(endpoint) if endpoint else bridge_state_dir() / "endpoint.json"
        try:
            details = json.loads(endpoint_path.read_text(encoding="utf-8"))
            port, self.token = details["port"], details["token"]
            self.pob_dir = Path(details["installDir"])
            if not isinstance(port, int) or not 1024 <= port <= 65535 or not isinstance(self.token, str) or len(self.token) < 32:
                raise ValueError("Некорректный адрес моста")
            if pob_dir and self.pob_dir.resolve() != Path(pob_dir).resolve():
                raise EngineError("APP_PATH_MISMATCH", "Мост запущен из другого каталога PoB")
            self.connection = socket.create_connection(("127.0.0.1", port), timeout=5)
            self.connection.settimeout(None)
            self.reader = self.connection.makefile("r", encoding="utf-8", newline="\n")
        except (OSError, ValueError, KeyError, TypeError) as error:
            raise EngineError("BRIDGE_NOT_RUNNING", "Нет связи с окном PoB. Выполните install-bridge и перезапустите PoB. " + str(error)) from None

    def send(self, line):
        self.connection.sendall(line.encode("utf-8"))

    def close(self):
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass
        self.reader.close()
        self.connection.close()
