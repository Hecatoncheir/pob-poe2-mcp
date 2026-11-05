"""Собрать закреплённые LuaJIT и lua-utf8 без установки в систему."""

import argparse
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tempfile
import zipfile

ROOT = Path(__file__).resolve().parents[1]
LOCK = json.loads((Path(__file__).with_name('native-lock.json')).read_text(encoding='utf-8'))


def run(*arguments):
    subprocess.run(arguments, check=True)


def checkout(base, name):
    target = base / name
    target.mkdir()
    run('git', '-C', str(target), 'init', '--quiet')
    run('git', '-C', str(target), 'fetch', '--depth=1', LOCK[name]['repository'], LOCK[name]['revision'])
    run('git', '-C', str(target), 'checkout', '--detach', 'FETCH_HEAD')
    return target


def build():
    if sys.platform not in {'linux', 'darwin'}:
        raise ValueError('На Windows используется runtime исходного PoB')
    destination = ROOT / 'pob_poe2_mcp/native'
    destination.mkdir(exist_ok=True)
    if sys.platform == 'darwin':
        os.environ.setdefault('MACOSX_DEPLOYMENT_TARGET', '11.0')
    with tempfile.TemporaryDirectory(prefix='pob-native-') as temporary:
        source = checkout(Path(temporary), 'luajit')
        utf8 = checkout(Path(temporary), 'luautf8')
        run('make', '-C', str(source), '-j2')
        darwin = sys.platform == 'darwin'
        library = 'libluajit-5.1.dylib' if darwin else 'libluajit-5.1.so.2'
        shutil.copy2(source / 'src/libluajit.so', destination / library)
        options = ['-bundle', '-undefined', 'dynamic_lookup'] if darwin else ['-shared', '-fPIC']
        run('cc', *options, '-O2', '-I' + str(source / 'src'), str(utf8 / 'lutf8lib.c'), '-o', str(destination / 'lua-utf8.so'))
        shutil.copy2(source / 'COPYRIGHT', destination / 'LICENSE-LuaJIT.txt')
        shutil.copy2(utf8 / 'LICENSE', destination / 'LICENSE-luautf8.txt')
        (destination / 'sources.json').write_text(json.dumps(LOCK, indent=2) + '\n', encoding='utf-8')
    target = 'macos-arm64' if sys.platform == 'darwin' and platform.machine() == 'arm64' else 'linux-x64'
    output = ROOT / 'dist' / ('pob-poe2-mcp-native-' + target + '.zip')
    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(destination.iterdir()):
            if path.is_file(): archive.write(path, 'native/' + path.name)
    print(output)


if __name__ == '__main__':
    argparse.ArgumentParser(description=__doc__).parse_args()
    build()
