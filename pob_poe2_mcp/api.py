"""Локальный API сборок: состояние и игровые расчёты принадлежат Lua."""

import json
import queue
import threading

from .engine import resolve_engine_dir, validate_engine
from .errors import EngineError
from .transport import AppTransport, ProcessTransport
from .wine_paths import linux_build_directory, wine_prefix

MAX_MESSAGE = 8 * 1024 * 1024


class BuildAPI:
    """Последовательный доступ к отдельной сессии или текущей сборке окна PoB."""

    def __init__(self, timeout=60, pob_dir=None, mode="engine", endpoint=None):
        self.mode = mode
        if mode == "app":
            self.transport = AppTransport(pob_dir=pob_dir, endpoint=endpoint)
            self.pob_dir = self.transport.pob_dir
        elif mode == "engine":
            self.pob_dir = validate_engine(resolve_engine_dir(pob_dir))
            self.transport = ProcessTransport(self.pob_dir)
        else:
            raise ValueError("Режим должен быть engine или app")
        self.timeout = timeout
        self.closed = False
        self.revision = 0
        self.counter = 0
        self.lock = threading.Lock()
        self.responses = queue.Queue()
        threading.Thread(target=self._read, daemon=True).start()
        try:
            self.capabilities = self.call("initialize")
        except Exception:
            self.close()
            raise

    def _read(self):
        try:
            while True:
                line = self.transport.reader.readline(MAX_MESSAGE + 1)
                if not line:
                    raise EngineError("ENGINE_STOPPED", "Процесс Lua завершился")
                if len(line.encode("utf-8")) > MAX_MESSAGE or not line.endswith("\n"):
                    raise EngineError("MESSAGE_TOO_LARGE", "Ответ превышает лимит")
                self.responses.put(json.loads(line))
        except Exception as error:
            self.responses.put(error)
        finally:
            self.transport.reader.close()

    def call(self, method, params=None):
        with self.lock:
            if self.closed:
                raise EngineError("ENGINE_STOPPED", "Соединение закрыто")
            self.counter += 1
            request = {"protocol": 1, "id": str(self.counter), "method": method,
                       "params": {"revision": self.revision, **(params or {})}}
            if self.transport.token:
                request["token"] = self.transport.token
            line = json.dumps(request, ensure_ascii=False) + "\n"
            if len(line.encode("utf-8")) > MAX_MESSAGE:
                raise EngineError("MESSAGE_TOO_LARGE", "Запрос превышает лимит")
            try:
                self.transport.send(line)
                response = self.responses.get(timeout=self.timeout)
            except OSError as error:
                self.close()
                raise EngineError("ENGINE_STOPPED", str(error)) from None
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
            result = response["result"]
            if self.mode == "app" and method == "getBuildDirectory" and result.get("wine") is not None:
                wine = result["wine"]
                prefix = wine_prefix(self.pob_dir, wine.get("prefix"))
                return {"directory": str(linux_build_directory(result["directory"], prefix, wine.get("workingDirectory")))}
            return result

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
        if not self.closed:
            self.closed = True
            self.transport.close()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
