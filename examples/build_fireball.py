"""Пример создания, проверки и повторной загрузки сборки через настоящий Lua."""

import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pob_poe2_mcp.api import BuildAPI


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, help="Записать XML в новый файл")
    parser.add_argument("--pob-dir", type=Path, help="Каталог движка PoB")
    args = parser.parse_args()
    with BuildAPI(pob_dir=args.pob_dir) as api:
        classes = api.call("getCatalog", {"kind": "classes"})["entries"]
        character = next(entry for entry in classes if entry["name"] == "Sorceress")
        api.call("createBuild", {"name": "Fireball API example", "level": 90, "classId": character["id"]})
        gem = api.call("getCatalog", {"kind": "gems", "query": "Fireball"})["entries"][0]
        api.call("addSkillGroup", {"label": "Fireball", "gems": [{"id": gem["id"], "level": 1}]})
        api.call("setConfig", {"values": {"enemyIsBoss": "None"}})
        checked = api.check([{"stat": "TotalDPS", "min": 1}])
        xml = api.call("exportBuild")["xml"]
        api.call("loadBuild", {"xml": xml})
        restored = api.call("getBuildReport")
        original = checked["report"]
        if abs(original["stats"]["TotalDPS"] - restored["stats"]["TotalDPS"]) > 1e-6:
            raise RuntimeError("Расчёт изменился после повторной загрузки")
        if args.output:
            with args.output.open("x", encoding="utf-8") as file:
                file.write(xml)
        print(json.dumps({"name": "Fireball API example", "source": restored["source"],
                          "TotalDPS": restored["stats"]["TotalDPS"],
                          "warnings": restored["warnings"], "checks": checked["checks"],
                          "roundTripPassed": True, "output": str(args.output) if args.output else None},
                         ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
