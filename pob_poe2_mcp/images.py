"""Создание PNG-отчётов из согласованного снимка Lua."""

from .bitmap import Canvas
from .errors import EngineError
from .image_text import TITLES, clean, content_rows, warning_lines
from .original_tree import draw_original_tree

BACKGROUND = (13, 19, 27)
PANEL = (20, 29, 40)
TEXT = (225, 231, 238)
MUTED = (145, 163, 181)
GOLD = (235, 188, 103)
STYLES = {'body': (TEXT, 18, False), 'heading': (GOLD, 19, True),
          'muted': (MUTED, 16, False), 'warning': ((249, 146, 131), 17, False)}


def validate_image_args(args):
    view = args.get('view', 'overview')
    if view in ('node', 'item') and args.get('id') is None:
        raise ValueError(f'Для раздела {view} нужен id из каталога или отчёта')
    if view == 'tree' and args.get('page', 1) != 1:
        raise ValueError('Дерево помещается на одной странице; используйте treeScope или query')


def fitting_prefix(canvas, text, width, size, bold):
    low, high = 1, len(text)
    while low < high:
        middle = (low + high + 1) // 2
        if canvas.measure(text[:middle], size, bold) <= width:
            low = middle
        else:
            high = middle - 1
    return low


def split_line(canvas, text, width, size, bold):
    if not text:
        return ['']
    lines, offset = [], 0
    while offset < len(text):
        fragment = text[offset:offset + max(64, width * 3)]
        end = fitting_prefix(canvas, fragment, width, size, bold)
        if end < len(fragment) and ' ' in fragment[:end]:
            end = fragment.rfind(' ', 0, end) + 1
        lines.append(fragment[:end].rstrip())
        offset = skip_spaces(text, offset + end)
    return lines


def skip_spaces(text, offset):
    while offset < len(text) and text[offset].isspace():
        offset += 1
    return offset


def wrapped_rows(canvas, rows):
    result = []
    for text, style in rows:
        _, size, bold = STYLES[style]
        for paragraph in text.split('\n'):
            result.extend((line, style) for line in split_line(canvas, paragraph, canvas.width - 100, size, bold))
    return result


def draw_header(canvas, report, title):
    info = report['snapshot']['buildInfo']
    canvas.rectangle(0, 0, canvas.width, canvas.height, BACKGROUND)
    canvas.rectangle(0, 0, canvas.width, 102, PANEL)
    canvas.rectangle(0, 0, 6, 102, GOLD)
    name = clean(info['name'])
    name_line = split_line(canvas, name, canvas.width - 64, 27, True)[0]
    canvas.text(32, 16, name_line, TEXT, 27, True)
    subtitle = f"{info['class']} / {info['ascendancy']} · Уровень {info['level']} · {title}"
    subtitle_lines = split_line(canvas, clean(subtitle), canvas.width - 64, 17, False)
    for index, line in enumerate(subtitle_lines[:2]):
        canvas.text(32, 53 + index * 21, line, MUTED, 17)


def draw_page(canvas, rows, page):
    per_page = max(1, (canvas.height - 172) // 27)
    page_count = max(1, (len(rows) + per_page - 1) // per_page)
    if page > page_count:
        raise ValueError(f'Страница {page} недоступна; всего страниц: {page_count}')
    start = (page - 1) * per_page
    for offset, (text, style) in enumerate(rows[start:start + per_page]):
        y = 118 + offset * 27
        color, size, bold = STYLES[style]
        if style == 'heading':
            canvas.rectangle(24, y - 1, canvas.width - 48, 26, PANEL)
        canvas.text(36, y, text, color, size, bold)
    return page_count


def render_build_image(data, args, pob_dir=None):
    validate_image_args(args)
    view, page = args.get('view', 'overview'), args.get('page', 1)
    width, height = args.get('width', 1600), args.get('height', 1100)
    report = data['report']
    tree_meta = {}
    with Canvas(width, height) as canvas:
        draw_header(canvas, report, TITLES[view])
        if view == 'tree':
            tree_meta = draw_original_tree(canvas, data, args, pob_dir)
            pages = 1
        else:
            rows = content_rows(data, view, args.get('id'), args.get('query', ''))
            pages = draw_page(canvas, wrapped_rows(canvas, rows), page)
        canvas.line(28, height - 44, width - 28, height - 44, (45, 60, 75))
        footer = f'Расчёт PoB · Предупреждений: {len(warning_lines(report))} · Страница {page}/{pages}'
        canvas.text(32, height - 34, footer, MUTED, 14)
        png = canvas.png()
    if len(png) > 4 * 1024 * 1024:
        raise EngineError('IMAGE_TOO_LARGE', 'PNG превышает 4 MiB; уменьшите ширину и высоту')
    metadata = {'view': view, 'page': page, 'pages': pages, 'width': width, 'height': height,
                'mimeType': 'image/png', 'warningCount': len(warning_lines(report)),
                'buildInfo': report['snapshot']['buildInfo'], 'tree': tree_meta}
    return png, metadata
