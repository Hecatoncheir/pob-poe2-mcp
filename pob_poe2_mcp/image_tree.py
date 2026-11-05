"""Подписи к оригинальному дереву и фильтр служебных связей."""

from .image_text import clean

LABEL_TYPES = {'ClassStart', 'AscendClassStart', 'Keystone', 'Notable', 'Socket'}


def visible_connections(tree):
    nodes = {node['id']: node for node in tree['nodes']}
    pairs = [(nodes[a], nodes[b]) for a, b in tree['edges'] if a in nodes and b in nodes]
    return [(a, b) for a, b in pairs if {a['type'], b['type']} != {'ClassStart', 'AscendClassStart'}]


def overlaps(rect, occupied):
    x, y, width, height = rect
    return any(x < ox + ow and x + width > ox and y < oy + oh and y + height > oy
               for ox, oy, ow, oh in occupied)


def draw_labels(canvas, nodes, position, rect, scale=1):
    occupied = []
    x, y, width, height = rect
    for node in nodes:
        if node['type'] not in LABEL_TYPES or not node['allocated']:
            continue
        label = f"{clean(node['name'])} (#{node['id']})"
        px, py = position(node)
        label_rect = px + max(8, node.get('drawSize', 0) * scale) + 5, py - 9, canvas.measure(label, 14) + 8, 20
        lx, ly, lw, lh = label_rect
        inside = lx >= x and ly >= y and lx + lw <= x + width and ly + lh <= y + height
        if inside and not overlaps(label_rect, occupied):
            canvas.rectangle(lx - 2, ly, lw, lh, (17, 24, 32))
            canvas.text(lx, ly, label, (225, 229, 233), 14)
            occupied.append(label_rect)
    return len(occupied)
