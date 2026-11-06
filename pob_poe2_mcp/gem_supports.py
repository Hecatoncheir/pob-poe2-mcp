"""Проверка черновика в отдельном Lua без изменения текущей сборки."""

from .api import BuildAPI


def compatible_supports(api, gems, timeout, group_id=None):
    xml = api.call('exportBuild')['xml']
    with BuildAPI(pob_dir=api.pob_dir, timeout=timeout) as preview:
        preview.call('loadBuild', {'xml': xml})
        result = preview.call('updateSkillGroup', {'groupId': group_id, 'gems': gems}) if group_id else preview.call('addSkillGroup', {'gems': gems})
        supports = preview.call('getCompatibleSupports', {'groupId': result['groupId']})
    return supports
