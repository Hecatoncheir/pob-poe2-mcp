"""Локальный API сборок: состояние и игровые расчёты принадлежат Lua."""

import json
import queue
import subprocess
import sys
import threading
from pathlib import Path

from .engine import resolve_engine_dir, validate_engine
from .errors import EngineError

PACKAGE_DIR = Path(__file__).resolve().parent
MAX_MESSAGE = 8 * 1024 * 1024


class BuildAPI:
    """Одна независимая сборка на процесс; вызовы выполняются последовательно."""

    def __init__(self, timeout=60, pob_dir=None):
        self.pob_dir = validate_engine(resolve_engine_dir(pob_dir))
        self.timeout = timeout
        self.revision = 0
        self.counter = 0
        self.lock = threading.Lock()
        self.responses = queue.Queue()
        self.process = subprocess.Popen(
            [sys.executable, "-X", "utf8", str(PACKAGE_DIR / "runner.py"),
             "--pob-dir", str(self.pob_dir)],
            cwd=self.pob_dir, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
            stderr=sys.stderr, text=True, encoding="utf-8", bufsize=1,
        )
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.capabilities = self.call("initialize")
        except Exception:
            self.close()
            raise

    def _read(self):
        try:
            while True:
                line = self.process.stdout.readline(MAX_MESSAGE + 1)
                if not line:
                    raise EngineError("ENGINE_STOPPED", "Процесс Lua завершился")
                if len(line.encode("utf-8")) > MAX_MESSAGE or not line.endswith("\n"):
                    raise EngineError("MESSAGE_TOO_LARGE", "Ответ превышает лимит")
                self.responses.put(json.loads(line))
        except Exception as error:
            self.responses.put(error)

    def call(self, method, params=None):
        with self.lock:
            self.counter += 1
            request = {"protocol": 1, "id": str(self.counter), "method": method,
                       "params": {"revision": self.revision, **(params or {})}}
            line = json.dumps(request, ensure_ascii=False) + "\n"
            if len(line.encode("utf-8")) > MAX_MESSAGE:
                raise EngineError("MESSAGE_TOO_LARGE", "Запрос превышает лимит")
            if self.process.poll() is not None:
                raise EngineError("ENGINE_STOPPED", "Перезапустите клиент")
            try:
                self.process.stdin.write(line)
                self.process.stdin.flush()
                response = self.responses.get(timeout=self.timeout)
            except queue.Empty:
                self.close()
                raise EngineError("TIMEOUT", "Lua не ответил; сессия закрыта") from None
            if isinstance(response, Exception):
                self.close()
                raise response
            if response.get("id") != request["id"]:
                self.close()
                raise EngineError("INVALID_RESPONSE", "Нарушена последовательность ответов")
            self.revision = response["revision"]
            if "error" in response:
                error = response["error"]
                raise EngineError(error["code"], error["message"])
            return response["result"]

    def check(self, targets=None):
        report = self.call("getBuildReport")
        checks = []
        for target in targets or []:
            stat = target["stat"]
            value = report["stats"].get(stat)
            passed = isinstance(value, (int, float)) and not isinstance(value, bool)
            if passed and "min" in target:
                passed = value >= target["min"]
            if passed and "max" in target:
                passed = value <= target["max"]
            checks.append({"stat": stat, "actual": value, "target": target, "passed": passed})
        return {"revision": self.revision, "report": report, "checks": checks,
                "targetsPassed": all(check["passed"] for check in checks) if checks else None}

    def close(self):
        if self.process.poll() is None:
            self.process.kill()
            self.process.wait(timeout=5)
        for stream in [self.process.stdin, self.process.stdout]:
            if stream:
                stream.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
