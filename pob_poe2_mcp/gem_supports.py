"""Проверка черновика в отдельном Lua без изменения текущей сборки."""

from .api import BuildAPI


def compatible_supports(api, gems, timeout):
    xml = api.call('exportBuild')['xml']
    with BuildAPI(pob_dir=api.pob_dir, timeout=timeout) as preview:
        preview.call('loadBuild', {'xml': xml})
        result = preview.call('addSkillGroup', {'gems': gems})
        supports = preview.call('getCompatibleSupports', {'groupId': result['groupId']})
    return supports
