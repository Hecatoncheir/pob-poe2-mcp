"""Сопоставить оригинальные изображения с ID Lua и закрепить SHA-256 без игровых правил."""

from concurrent.futures import ThreadPoolExecutor
import hashlib
from html.parser import HTMLParser
import json
from pathlib import Path
import sys
from urllib.request import Request, urlopen

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from pob_poe2_mcp.api import BuildAPI

SOURCE = 'https://poe2db.tw/us/Support_Gems'
HEADERS = {'User-Agent': 'pob-poe2-mcp asset catalogue', 'Referer': 'https://poe2db.tw/'}
ALIASES = {"Morrigan's Insight": "Mórrigan's Insight", "Oisin's Oath": "Oisín's Oath"}


class SupportImages(HTMLParser):
    def __init__(self):
        super().__init__()
        self.by_name, self.by_variant = {}, {}
        self.image, self.alt, self.anchor, self.text = None, None, False, ''

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'tr':
            self.image, self.alt = None, None
        if tag == 'a':
            self.anchor = any(value.startswith('gem') for value in attrs.get('class', '').split())
            self.text = ''
        if tag == 'img' and 'https://cdn.poe2db.tw/image/Art/' in attrs.get('src', ''):
            self.image, self.alt = attrs['src'], attrs.get('alt')

    def handle_data(self, text):
        if self.anchor:
            self.text += text

    def handle_endtag(self, tag):
        if tag != 'a':
            return
        if self.anchor and self.text.strip() and self.image:
            self.by_name[self.text.strip()] = self.image
            if self.alt:
                self.by_variant[self.alt] = self.image
        self.anchor = False


def read(url):
    with urlopen(Request(url, headers=HEADERS), timeout=30) as response:
        data = response.read(1024 * 1024 * 8 + 1)
    if len(data) > 1024 * 1024 * 8:
        raise ValueError('Слишком большой источник изображений')
    return data


def main():
    html = read(SOURCE)
    index = SupportImages()
    index.feed(html.decode('utf-8'))
    with BuildAPI() as engine:
        gems = []
        while True:
            page = engine.call('getCatalog', {'kind': 'gems', 'limit': 200, 'offset': len(gems)})
            gems.extend(page['entries'])
            if len(gems) >= page['total']:
                break
    mapped, missing = {}, []
    for gem in gems:
        if not gem['support']:
            continue
        url = index.by_variant.get(gem.get('variantId')) or index.by_name.get(ALIASES.get(gem['name'], gem['name']))
        if url:
            mapped[gem['id']] = url
        else:
            missing.append(gem['name'])
    def download(url):
        data = read(url)
        if data[:4] != b'RIFF' or data[8:12] != b'WEBP':
            raise ValueError('Ожидалось оригинальное изображение WebP: ' + url)
        return url, hashlib.sha256(data).hexdigest()
    with ThreadPoolExecutor(max_workers=4) as pool:
        hashes = dict(pool.map(download, sorted(set(mapped.values()))))
    manifest = {'source': SOURCE, 'sourceSha256': hashlib.sha256(html).hexdigest(),
                'copyright': 'Grinding Gear Games',
                'icons': {key: {'url': url, 'sha256': hashes[url]} for key, url in sorted(mapped.items())}}
    (ROOT / 'pob_poe2_mcp/data/gem-icons.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print('Изображений:', len(mapped), 'Не найдено:', missing)


if __name__ == '__main__':
    main()
