"""Проверка черновика в отдельном Lua без изменения текущей сборки."""

import hashlib

from .api import BuildAPI
from .errors import EngineError


def _apply_group(api, gems, group_id):
    if group_id is None:
        return api.call('addSkillGroup', {'gems': gems})['groupId']
    return api.call('updateSkillGroup', {'groupId': group_id, 'gems': gems})['groupId']


def compatible_supports(api, gems, timeout, group_id=None, target_index=None):
    xml = api.call('exportBuild')['xml']
    with BuildAPI(pob_dir=api.pob_dir, timeout=timeout) as preview:
        preview.call('loadBuild', {'xml': xml})
        preview_group = _apply_group(preview, gems, group_id)
        supports = preview.call('getCompatibleSupports', {
            'groupId': preview_group,
            **({'targetIndex': target_index} if target_index is not None else {}),
        })
        supports['sockets']['capacity'] = None
        supports['sockets']['capacityStatus'] = 'unavailable'
        supports['warnings'] = preview.call('getBuildReport').get('warnings', [])
    return supports


def preview_support(api, gems, target_index, support_id, timeout, group_id=None):
    """Сравнить DPS выбранного умения в черновике и с одной новой поддержкой."""
    xml = api.call('exportBuild')['xml']
    return _preview_xml(api.pob_dir, xml, gems, target_index, support_id, timeout, group_id)


def _preview_xml(pob_dir, xml, gems, target_index, support_id, timeout, group_id):
    with BuildAPI(pob_dir=pob_dir, timeout=timeout) as preview:
        return _measure(preview, xml, gems, target_index, support_id, group_id)


def _measure(preview, xml, gems, target_index, support_id, group_id):
    if any(gem['id'] == support_id for gem in gems):
        raise EngineError('INVALID_REQUEST', 'Эта поддержка уже есть в группе')
    preview.call('loadBuild', {'xml': xml})
    preview_group = _apply_group(preview, gems, group_id)
    target = {'groupId': preview_group, 'targetIndex': target_index}
    before = preview.call('measureSupportPreview', {**target, 'supportId': support_id})
    # После применения черновика индексы принадлежат новой группе.
    updated = [{**gem, 'sourceIndex': index} for index, gem in enumerate(gems, 1)]
    updated.append({'id': support_id, 'level': 1, 'quality': 0, 'enabled': True})
    _apply_group(preview, updated, preview_group)
    after = preview.call('measureSupportPreview', {**target, 'effectId': before['effectId']})
    if (before['part'], before['statSet']) != (after['part'], after['statSet']):
        raise EngineError('CALCULATION_FAILED', 'Изменился вариант выбранного умения')
    warnings = preview.call('getBuildReport').get('warnings', [])
    first, last = before.get('dps'), after.get('dps')
    return {'source': 'original-lua', 'before': first, 'after': last,
            'delta': last - first if first is not None and last is not None else None,
            'warnings': warnings}


def compare_supports(api, gems, target_index, support_ids, timeout, group_id=None):
    """Рассчитать кандидатов из одного XML; ошибка одного не скрывает остальные."""
    if not 1 <= len(support_ids) <= 8 or len(set(support_ids)) != len(support_ids):
        raise EngineError('INVALID_REQUEST', 'Выберите от 1 до 8 разных поддержек')
    xml = api.call('exportBuild')['xml']
    revision = api.revision
    rows = []
    with BuildAPI(pob_dir=api.pob_dir, timeout=timeout) as preview:
        for support_id in support_ids:
            try:
                result = _measure(preview, xml, gems, target_index, support_id, group_id)
            except EngineError as error:
                result = {'error': {'code': error.code, 'message': str(error)}}
            rows.append({'supportId': support_id, **result})
    return {'source': 'original-lua', 'baseRevision': revision,
            'xmlHash': hashlib.sha256(xml.encode('utf-8')).hexdigest(), 'entries': rows}
