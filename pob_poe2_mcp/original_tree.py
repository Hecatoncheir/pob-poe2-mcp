"""Изображение оригинальных команд PassiveTreeView с текстурами установленного PoB."""

from .d3d11 import Renderer
from .image_tree import draw_labels, visible_connections
from .texture_data import Textures
from .image_text import clean


def draw_original_tree(canvas, data, args, pob_dir):
    if 'scene' not in data:
        raise ValueError('Обновите MCP: в данных нет команд оригинальной отрисовки дерева')
    scene, tree = data['scene'], data['tree']
    textures = Textures(pob_dir)
    with Renderer(scene['width'], scene['height']) as renderer:
        for command in scene['commands']:
            if command.get('mask') is not None:
                raise ValueError('Маска текстуры требует неподдерживаемого режима отрисовки')
            key, mips = textures.get(command)
            texture = renderer.texture(key, mips)
            renderer.draw(command, texture)
        canvas.paste(28, 142, renderer.raster())
        texture_count = len(renderer.textures)
    labels = 0
    if args.get('showLabels', False):
        position = lambda node: (28 + scene['offsetX'] + node['x'] * scene['scale'],
                                 142 + scene['offsetY'] + node['y'] * scene['scale'])
        labels = draw_labels(canvas, tree['nodes'], position, (28, 142, scene['width'], scene['height']), scene['scale'])
    canvas.text(32, 112, 'Очки дерева: ' + clean(data['report'].get('pointDisplay', '')), (145, 163, 181), 17)
    return {'nodeCount': len(tree['nodes']), 'allocatedNodeCount': sum(node['allocated'] for node in tree['nodes']),
            'edgeCount': len(visible_connections(tree)), 'visibleLabels': labels,
            'commandCount': len(scene['commands']), 'textureCount': texture_count, 'scale': scene['scale'],
            'assetWarnings': [], 'renderer': 'PassiveTreeView Lua / Direct3D 11 WARP',
            'representation': 'Оригинальные размеры, текстуры, рамки, фоны и дуги PoB. Связи класса с восхождением скрыты.'}
