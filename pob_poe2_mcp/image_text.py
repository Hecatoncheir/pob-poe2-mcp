"""Разделы изображений: только данные исходного отчёта Lua."""

import json
import re

TITLES = {'overview': 'Сводка сборки', 'tree': 'Дерево пассивных умений', 'stats': 'Характеристики',
          'skills': 'Умения и камни', 'items': 'Предметы', 'config': 'Условия расчёта',
          'notes': 'Заметки', 'warnings': 'Предупреждения', 'node': 'Пассивное умение',
          'item': 'Предмет', 'all': 'Полный отчёт о сборке'}
STAT_LABELS = {'Life': 'Жизнь', 'EnergyShield': 'Энергетический щит', 'Mana': 'Мана', 'Spirit': 'Дух',
               'TotalDPS': 'DPS выбранного умения', 'TotalEHP': 'Эффективный запас здоровья',
               'Armour': 'Броня', 'Evasion': 'Уклонение', 'EvadeChance': 'Шанс уклонения, %',
               'FireResist': 'Сопротивление огню, %', 'ColdResist': 'Сопротивление холоду, %',
               'LightningResist': 'Сопротивление молнии, %', 'ChaosResist': 'Сопротивление хаосу, %',
               'Str': 'Сила', 'Dex': 'Ловкость', 'Int': 'Интеллект', 'BlockChance': 'Шанс блока, %',
               'SpiritUnreserved': 'Свободный дух'}
SUMMARY_STATS = ['TotalDPS', 'Life', 'EnergyShield', 'Mana', 'Spirit', 'SpiritUnreserved',
                 'Armour', 'Evasion', 'EvadeChance', 'BlockChance', 'FireResist', 'ColdResist',
                 'LightningResist', 'ChaosResist', 'Str', 'Dex', 'Int']


def clean(value):
    text = re.sub(r'\^x[0-9a-fA-F]{6}|\^[0-9]', '', str(value))
    text = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f]', '', text)
    return text.replace('\t', '    ').encode('utf-8', errors='replace').decode('utf-8')


def value_text(value):
    if isinstance(value, bool):
        return 'да' if value else 'нет'
    if isinstance(value, float):
        return format(value, '.8g')
    if isinstance(value, (dict, list)):
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return clean(value)


def row(text, style='body'):
    return clean(text), style


def gem_warnings(group):
    return [f"Камень {gem['name']}: {clean(gem['error'])}" for gem in group.get('gems', []) if gem.get('error')]


def item_warnings(item):
    return [f"Предмет #{item['id']} {item['name']}: не поддерживается {clean(modifier['line'])}"
            for modifier in item.get('unsupported', [])]


def warning_lines(report):
    lines = [clean(text) for text in report.get('warnings', [])]
    for group in report.get('groups', []):
        lines.extend(gem_warnings(group))
    for item in report.get('items', []):
        lines.extend(item_warnings(item))
    for block in report.get('customMods', []):
        lines.extend('Пользовательский модификатор: не распознан ' + clean(modifier['line'])
                     for modifier in block.get('unparsed', []))
    return lines


def warnings(report):
    lines = warning_lines(report)
    yield row('Предупреждения и неподдерживаемые модификаторы', 'heading')
    yield row('Включены ошибки камней, предметов и пользовательских модификаторов.', 'muted')
    for line in lines:
        yield row(line, 'warning')
    if not lines:
        yield row('В доступном отчёте PoB предупреждений нет.')


def stats(report):
    yield row('Показатели исходного расчёта PoB', 'heading')
    yield row('Точные имена показателей сохранены. Отсутствующий показатель не считается нулём.', 'muted')
    for key, value in sorted(report['stats'].items()):
        label = STAT_LABELS.get(key)
        yield row(f"{key}{' — ' + label if label else ''}: {value_text(value)}")


def skills(report):
    for group in report.get('groups', []):
        state = 'включена' if group['enabled'] else 'выключена'
        yield row(f"Группа #{group['id']}: {group['label']} · {state}", 'heading')
        for gem in group['gems']:
            state = 'включён' if gem['enabled'] else 'выключен'
            yield row(f"{gem['name']} · уровень {gem['level']} · качество {gem['quality']}% · {state}")
            if gem.get('error'):
                yield row(gem['error'], 'warning')
    if not report.get('groups'):
        yield row('Группы умений не добавлены.')


def item_rows(report, item):
    yield row(f"#{item['id']}: {item['name']} · {item['base']}", 'heading')
    slots = [slot['name'] for slot in report.get('slots', []) if slot['itemId'] == item['id']]
    yield row('Слоты: ' + (', '.join(slots) or 'в списке предметов, не надет'), 'muted')
    for line in item['raw'].splitlines():
        yield row(line)
    for modifier in item.get('unsupported', []):
        yield row('Не поддерживается: ' + modifier['line'], 'warning')
    yield row('')


def items(report):
    for item in report.get('items', []):
        yield from item_rows(report, item)
    if not report.get('items'):
        yield row('Предметы не добавлены.')


def mapping_rows(title, values):
    yield row(title, 'heading')
    for key, value in sorted(values.items()):
        yield row(f'{key}: {value_text(value)}')
    if not values:
        yield row('Нет значений.', 'muted')


def config(report):
    yield from mapping_rows('Установленные параметры расчёта', report.get('config', {}))
    yield from mapping_rows('Подсказки PoB — не отдельные заданные параметры', report.get('configPlaceholders', {}))
    yield row('Пользовательские модификаторы — предположения автора', 'heading')
    for block in report.get('customMods', []):
        state = 'включён' if block['enabled'] else 'выключен'
        yield row(f"{block['title']} · {state}", 'muted')
        for line in block['text'].splitlines():
            yield row(line)
    if not report.get('customMods'):
        yield row('Пользовательских модификаторов нет.')


def notes(report):
    yield row('Заметки автора сборки', 'heading')
    for line in (report.get('notes') or 'Заметок нет.').splitlines():
        yield row(line)


def overview(report):
    info = report['snapshot']['buildInfo']
    selected = info['groups']['selected']
    groups = info['groups']['entries']
    main = next((group['label'] for group in groups if group['id'] == selected), 'не выбрано')
    yield row('Основное умение: ' + main, 'heading')
    for key in SUMMARY_STATS:
        if key in report['stats']:
            yield row(f"{STAT_LABELS[key]}: {value_text(report['stats'][key])}")
    yield row('Очки дерева: ' + clean(report.get('pointDisplay', 'нет данных')), 'muted')
    yield row(f"Групп умений: {len(report.get('groups', []))} · Предметов в списке: {len(report.get('items', []))}", 'muted')
    yield row('Условия расчёта', 'heading')
    for key in ['enemyIsBoss', 'enemyLevel', 'conditionEnemyChilled', 'conditionUsingFlask', 'resistancePenalty']:
        if key in report['config']:
            yield row(f'{key}: {value_text(report["config"][key])}')
    yield from warnings(report)


def sets_and_slots(report):
    yield row('Наборы сборки и слоты', 'heading')
    for kind, sets in report.get('sets', {}).items():
        active = report.get('activeSets', {}).get(kind)
        for entry in sets:
            yield row(f"{kind} #{entry['id']}: {entry.get('title', '')}" + (' · активен' if entry['id'] == active else ''))
    for slot in report.get('slots', []):
        yield row(f"{slot['name']}: предмет #{slot['itemId']}")
    yield row('Назначенные узлы', 'heading')
    yield row(', '.join(str(node) for node in report.get('allocatedNodes', [])))


def all_sections(report):
    for section in [overview, stats, skills, items, config, sets_and_slots, notes]:
        yield from section(report)


SECTIONS = {'overview': overview, 'stats': stats, 'skills': skills, 'items': items,
            'config': config, 'notes': notes, 'warnings': warnings, 'all': all_sections}


def detail_rows(data, view, object_id):
    if object_id is None:
        raise ValueError(f'Для раздела {view} нужен id из каталога или отчёта')
    if view == 'item':
        item = next((item for item in data['report']['items'] if item['id'] == object_id), None)
        if item is None:
            raise ValueError('Предмет с таким id не найден')
        return list(item_rows(data['report'], item))
    tooltip = data['tooltip']
    rows = [row(f'Узел #{object_id}', 'heading')]
    rows.extend(row(line.get('text', '')) for line in tooltip['lines'])
    rows.append(row('Маршрут / зависимости: ' + ', '.join(map(str, tooltip.get('path', []))), 'muted'))
    if tooltip.get('note'):
        rows.append(row('Заметка: ' + tooltip['note']))
    return rows


def content_rows(data, view, object_id=None, query=''):
    if view in ('node', 'item'):
        rows = detail_rows(data, view, object_id)
    else:
        rows = list(SECTIONS[view](data['report']))
    if query:
        rows = [line for line in rows if query.casefold() in line[0].casefold()]
    return rows or [row('По заданному фильтру ничего не найдено.', 'muted')]
