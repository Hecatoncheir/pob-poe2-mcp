"""Сопоставление путей Linux и дисков префикса Wine."""

import os
from pathlib import Path, PureWindowsPath

from .errors import EngineError


def wine_prefix(install=None, reported=None):
    if reported and Path(reported).is_absolute():
        return Path(reported)
    if install:
        for parent in Path(install).parents:
            if parent.name == "drive_c":
                return parent.parent
    return Path(os.environ.get("WINEPREFIX") or Path.home() / ".wine").expanduser()


def wine_installations():
    drive = wine_prefix() / "drive_c"
    for directory in [drive / "Program Files", drive / "Program Files (x86)",
                      *(drive / "users").glob("*/AppData/Roaming"),
                      *(drive / "users").glob("*/AppData/Local")]:
        yield from directory.glob("Path of Building*")


def _drives(prefix):
    devices = prefix / "dosdevices"
    if devices.is_dir():
        return {entry.name.lower(): entry.resolve() for entry in devices.glob("[a-zA-Z]:")
                if entry.is_dir()}
    return {"c:": prefix / "drive_c", "z:": Path("/")}


def wine_path(path, prefix):
    path = Path(path).resolve()
    drives = _drives(prefix)
    for drive, root in drives.items():
        if root == Path("/"):
            return f"{drive.upper()}/{path.relative_to(root).as_posix()}"
    matches = [(drive, root) for drive, root in drives.items() if path.is_relative_to(root)]
    if matches:
        drive, root = max(matches, key=lambda match: len(match[1].parts))
        return f"{drive.upper()}/{path.relative_to(root).as_posix()}"
    raise EngineError("WINE_PATH_UNAVAILABLE", "Каталог моста недоступен через диски выбранного префикса Wine.")


def _existing_name(parent, name):
    exact = parent / name
    if exact.exists() or not parent.is_dir():
        return exact
    return next((entry for entry in parent.iterdir() if entry.name.casefold() == name.casefold()), exact)


def linux_build_directory(directory, prefix, working_directory=None):
    if directory.startswith("/"):
        return Path(directory).resolve()
    location = PureWindowsPath(directory)
    if not location.is_absolute() and working_directory:
        location = PureWindowsPath(working_directory) / location
    root = _drives(prefix).get(location.drive.lower())
    if root is None or not location.is_absolute():
        raise EngineError("BUILD_DIRECTORY_UNAVAILABLE", "Не удалось сопоставить папку сборок с диском Wine.")
    for name in location.parts[1:]:
        root = _existing_name(root, name)
    return root.resolve()
