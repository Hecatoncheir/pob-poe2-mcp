"""Проверить версию релиза, извлечь changelog и записать SHA-256 пакетов."""

import argparse
import ast
import hashlib
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parents[1]


def version_from_tag(tag):
    if not re.fullmatch(r"v(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", tag):
        raise ValueError("Нужен стабильный тег вида v0.2.0")
    return tag[1:]


def changelog_entry(changelog, version):
    heading = re.search(rf"^## \[{re.escape(version)}\] - \d{{4}}-\d{{2}}-\d{{2}}\s*$", changelog, re.MULTILINE)
    if not heading:
        raise ValueError(f"В CHANGELOG.md нет раздела [{version}] с датой")
    rest = changelog[heading.end():]
    end = re.search(r"^## ", rest, re.MULTILINE)
    body = rest[:end.start()] if end else rest
    if not body.strip():
        raise ValueError(f"Раздел changelog для {version} пуст")
    return body.strip() + "\n"


def package_version(root):
    module = ast.parse((root / "pob_poe2_mcp/__init__.py").read_text(encoding="utf-8"))
    for statement in module.body:
        if isinstance(statement, ast.Assign) and any(isinstance(target, ast.Name) and target.id == "__version__" for target in statement.targets):
            return ast.literal_eval(statement.value)
    raise ValueError("Не найдена __version__ пакета")


def validate(tag, root=ROOT):
    version = version_from_tag(tag)
    project = tomllib.loads((root / "pyproject.toml").read_text(encoding="utf-8"))["project"]
    if project["version"] != version or package_version(root) != version:
        raise ValueError("Версия тега должна совпадать с pyproject.toml и __version__")
    return changelog_entry((root / "CHANGELOG.md").read_text(encoding="utf-8"), version)


def prepare(tag, directory, root=ROOT):
    notes = validate(tag, root)
    version = version_from_tag(tag)
    packages = [directory / f"pob_poe2_mcp-{version}-py3-none-any.whl", directory / "pob-poe2-mcp-windows-x64.zip"]
    for package in packages:
        if not package.is_file():
            raise ValueError(f"Нет собранного пакета: {package}")
    sums = [hashlib.sha256(package.read_bytes()).hexdigest() + "  " + package.name for package in packages]
    (directory / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    (directory / "RELEASE_NOTES.md").write_text(notes, encoding="utf-8")
    return packages


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--artifacts", type=Path, default=ROOT / "dist")
    parser.add_argument("--check-only", action="store_true")
    args = parser.parse_args()
    try:
        if args.check_only:
            validate(args.tag)
        else:
            prepare(args.tag, args.artifacts)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Ошибка релиза: {error}\n")
    print(f"Версия, changelog и пакеты {args.tag} проверены")
