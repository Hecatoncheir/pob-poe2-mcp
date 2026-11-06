"""Оригинальные изображения GGG с закреплёнными адресами и SHA-256; игровые данные не загружаются."""

import hashlib
import json
import os
from pathlib import Path
import tempfile
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

MANIFEST = Path(__file__).parent / 'data/gem-icons.json'
MAX_IMAGE = 128 * 1024


def allowed(url):
    parsed = urlsplit(url)
    if parsed.scheme != 'https' or parsed.netloc != 'cdn.poe2db.tw' or not parsed.path.startswith('/image/Art/') or parsed.query or parsed.fragment:
        raise ValueError('Недопустимый источник иконки')


class RemoteGemImages:
    def __init__(self, cache=None):
        self.entries = json.loads(MANIFEST.read_text(encoding='utf-8'))['icons']
        self.cache = Path(cache or os.environ.get('POB_MCP_GEM_CACHE', Path.home() / '.cache/pob-poe2-mcp/gem-icons'))

    def read(self, gem_id):
        entry = self.entries.get(gem_id)
        if not entry:
            raise ValueError('Оригинальное изображение камня не найдено')
        allowed(entry['url'])
        file = self.cache / (entry['sha256'] + '.webp')
        if file.is_file() and file.stat().st_size <= MAX_IMAGE:
            data = file.read_bytes()
            if self._valid(data, entry['sha256']):
                return data, entry['url']
        request = Request(entry['url'], headers={'User-Agent': 'pob-poe2-mcp gem icons', 'Referer': 'https://poe2db.tw/'})
        with urlopen(request, timeout=6) as response:
            allowed(response.geturl())
            data = response.read(MAX_IMAGE + 1)
        if not self._valid(data, entry['sha256']):
            raise ValueError('Иконка не прошла проверку SHA-256 или формата WebP')
        self._save(file, data)
        return data, entry['url']

    def _valid(self, data, expected):
        return len(data) <= MAX_IMAGE and data[:4] == b'RIFF' and data[8:12] == b'WEBP' and hashlib.sha256(data).hexdigest() == expected

    def _save(self, file, data):
        temporary = None
        try:
            file.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=file.parent, delete=False) as output:
                temporary = Path(output.name)
                output.write(data)
            temporary.replace(file)
        except OSError:
            pass
        finally:
            if temporary and temporary.exists():
                try:
                    temporary.unlink()
                except OSError:
                    pass
