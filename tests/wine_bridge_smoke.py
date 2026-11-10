"""Проверяет настоящий мост Wine с тестовыми ответами API персонажей."""

import os
from pathlib import Path
import subprocess
import sys
import time

from pob_poe2_mcp.api import BuildAPI
from pob_poe2_mcp.bridge import install_bridge
from pob_poe2_mcp.errors import EngineError


FIXTURE = '''
local init = launch.OnInit
function launch:OnInit(...)
    init(self, ...)
    main.lastToken = "test-token"
    main.lastRefreshToken = "test-refresh"
    main.tokenExpiry = os.time() + 3600
end
local download = launch.DownloadPage
function launch:DownloadPage(url, callback, options)
    local endpoint = url:match("^https://api%.pathofexile%.com(/character/poe2.*)$")
    if not endpoint then return download(self, url, callback, options) end
    assert(options.header == "Authorization: Bearer test-token")
    local character = { name = "WineTest", class = "Witch", level = 90, league = "Standard",
        passives = { hashes = {} } }
    local result = endpoint == "/character/poe2" and { characters = { character } } or { character = character }
    callback({ header = "HTTP/1.1 200 OK\\r\\n", body = require("dkjson").encode(result) })
end
'''


def wait_for_window(directory, process):
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and process.poll() is None:
        try:
            return BuildAPI(mode="app", pob_dir=directory, timeout=5)
        except EngineError as error:
            if error.code not in {"BRIDGE_NOT_RUNNING", "ENGINE_STOPPED", "TIMEOUT"}:
                raise
        except OSError:
            pass
        time.sleep(1)
    raise RuntimeError("Окно PoB под Wine не подключилось к мосту.")


def main(portable):
    executable = next(Path(portable).resolve().rglob("Path of Building-PoE2.exe"))
    prefix = Path(os.environ["WINEPREFIX"]).resolve()
    assert not prefix.exists(), "Для теста нужен новый префикс Wine."
    subprocess.run(["wineboot", "-i"], check=True, timeout=90)
    launch = executable.with_name("Launch.lua")
    with launch.open("a", encoding="utf-8") as script:
        script.write(FIXTURE)
    install_bridge(executable.parent)
    process = subprocess.Popen(["wine", str(executable)], cwd=executable.parent)
    try:
        with wait_for_window(executable.parent, process) as api:
            assert api.capabilities["platform"] == "linux-app", api.capabilities
            directory = Path(api.call("getBuildDirectory")["directory"])
            assert directory.is_dir(), directory
            assert directory.is_relative_to(executable.parent) or directory.is_relative_to(prefix), directory
            expected = {"name": "WineTest", "class": "Witch", "level": 90, "league": "Standard"}
            assert api.call("listCharacters") == {"characters": [expected]}
            assert api.call("getCharacter", {"name": "WineTest"}) == {
                "character": {**expected, "passives": {"hashes": []}},
            }
    finally:
        subprocess.run(["wineserver", "-k"], check=False, timeout=20)
        process.wait(timeout=20)
    print("Мост Wine вернул папку сборок, список и данные персонажа.")


if __name__ == "__main__":
    main(sys.argv[1])
