-- Изменение группы сохраняет остальные поля исходной сериализацией SkillsTab.
return function(methods, fail, finish)
local function savedGroup(index)
	local skills = { elem = "Skills", attrib = {} }
	build.skillsTab:Save(skills)
	for _, skillSet in ipairs(skills) do
		if tonumber(skillSet.attrib.id) == build.skillsTab.activeSkillSetId then return skillSet[index] end
	end
end
local function replacementGem(input, previous, oldGem, used)
	local data = build.data.gems[input.id]
	if not data then fail("INVALID_REQUEST", "Неизвестный ID камня") end
	local node = { elem = "Gem", attrib = {} }
	if input.sourceIndex then
		if not oldGem or oldGem.gemId ~= input.id or used[input.sourceIndex] then
			fail("STALE_GROUP", "Состав группы изменился; откройте редактор заново")
		end
		used[input.sourceIndex] = true
		node = copyTable(previous, true)
	end
	local level, quality = input.level or 1, input.quality or 0
	if type(level) ~= "number" or level % 1 ~= 0 or level < 1 or level > 40 or type(quality) ~= "number" or quality % 1 ~= 0 or quality < 0 or quality > 100 then
		fail("INVALID_REQUEST", "Некорректный уровень или качество камня")
	end
	node.attrib.nameSpec, node.attrib.skillId = data.name, data.grantedEffectId
	node.attrib.gemId, node.attrib.variantId = data.gameId, data.variantId
	node.attrib.level, node.attrib.quality, node.attrib.enabled = tostring(level), tostring(quality), tostring(input.enabled ~= false)
	return node
end
function methods.updateSkillGroup(params)
	local groups = build.skillsTab.socketGroupList
	local old = groups[params.groupId]
	if not old then fail("INVALID_REQUEST", "Группа не найдена") end
	if old.source and old.source ~= "" then fail("INVALID_REQUEST", "Группа создана предметом; измените источник умения") end
	if type(params.gems) ~= "table" or #params.gems < 1 or #params.gems > 12 then fail("INVALID_REQUEST", "Нужен список из 1–12 камней") end
	local previous = savedGroup(params.groupId)
	local node = { elem = "Skill", attrib = copyTable(previous.attrib, true) }
	if params.label ~= nil then
		if type(params.label) ~= "string" or #params.label > 200 then fail("INVALID_REQUEST", "Некорректная метка") end
		node.attrib.label = params.label
	end
	local used = {}
	for _, input in ipairs(params.gems) do
		node[#node + 1] = replacementGem(input, previous[input.sourceIndex], old.gemList[input.sourceIndex], used)
	end
	build.skillsTab:LoadSkill(node, build.skillsTab.activeSkillSetId)
	local replacement = table.remove(groups)
	groups[params.groupId] = replacement
	build.skillsTab:SetDisplayGroup(replacement)
	local result = finish()
	result.groupId = params.groupId
	return result
end
end
