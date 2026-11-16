"""Проверка черновика в отдельном Lua без изменения текущей сборки."""

from .api import BuildAPI
from .errors import EngineError


def _apply_group(api, gems, group_id):
    if group_id is None:
        return api.call('addSkillGroup', {'gems': gems})['groupId']
    return api.call('updateSkillGroup', {'groupId': group_id, 'gems': gems})['groupId']


def compatible_supports(api, gems, timeout, group_id=None):
    xml = api.call('exportBuild')['xml']
    with BuildAPI(pob_dir=api.pob_dir, timeout=timeout) as preview:
        preview.call('loadBuild', {'xml': xml})
        preview_group = _apply_group(preview, gems, group_id)
        supports = preview.call('getCompatibleSupports', {'groupId': preview_group})
    return supports


def preview_support(api, gems, target_index, support_id, timeout, group_id=None):
    """Сравнить DPS выбранного умения в черновике и с одной новой поддержкой."""
    if any(gem['id'] == support_id for gem in gems):
        raise EngineError('INVALID_REQUEST', 'Эта поддержка уже есть в группе')
    xml = api.call('exportBuild')['xml']
    with BuildAPI(pob_dir=api.pob_dir, timeout=timeout) as preview:
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
    first, last = before.get('dps'), after.get('dps')
    return {'source': 'original-lua', 'before': first, 'after': last,
            'delta': last - first if first is not None and last is not None else None}
