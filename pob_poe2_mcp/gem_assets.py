"""Оригинальные слои иконок камней из таблицы Lua; пути от клиента не принимаются."""

import base64
from concurrent.futures import ThreadPoolExecutor

from .tree_scene_assets import SceneAssets
from .gem_remote_images import RemoteGemImages, MAX_IMAGE


class GemAssets:
    def __init__(self, pob_dir):
        self.images = SceneAssets(pob_dir)
        self.remote = RemoteGemImages()

    def render(self, descriptors):
        with ThreadPoolExecutor(max_workers=4) as pool:
            return {'icons': list(pool.map(self._icon, descriptors['icons']))}

    def _icon(self, asset):
        result = {'id': asset['id']}
        try:
            if 'error' in asset:
                image, source = self.remote.read(asset['id'])
                result.update(mimeType='image/webp', source=source)
            else:
                image = self.images.encoded(asset['file'], asset['index'])
                result.update(mimeType='image/png', source='original-pob')
            if len(image) > MAX_IMAGE:
                raise ValueError('Иконка превышает лимит размера')
            result['data'] = base64.b64encode(image).decode('ascii')
        except (ValueError, OSError) as error:
            result['error'] = str(error)
        return result
