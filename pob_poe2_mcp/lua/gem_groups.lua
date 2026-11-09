-- Изменение группы сохраняет остальные поля исходной сериализацией SkillsTab.
return function(methods, fail, finish, granted)
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
local function loadGroup(node)
	local skills = build.skillsTab
	skills:LoadSkill(node, skills.activeSkillSetId)
	return table.remove(skills.socketGroupList)
end
local function updateGranted(group, params, scope)
	local primary = group.gemList[1]
	local first = params.gems[1]
	if first.sourceIndex ~= 1 or (first.id ~= primary.skillId and first.id ~= primary.gemId
		and first.id ~= (primary.gemData and primary.gemData.id)) then
		fail("STALE_GROUP", "Умение от предмета изменилось; откройте редактор заново")
	end

	local groups = build.skillsTab.socketGroupList
	local target, targetIndex = group, params.groupId
	local offset = 0
	if scope == "slot" then
		target, targetIndex = granted.slotGroup(build, group.slot)
		offset = 1
	end
	local previous = targetIndex and savedGroup(targetIndex)
	local node = { elem = "Skill", attrib = previous and previous.attrib or { slot = group.slot, enabled = "true" } }
	if scope == "skill" then node[1] = previous[1] end
	local used = {}
	local added = {}
	for i = 2, #params.gems do
		local input = params.gems[i]
		local data = build.data.gems[input.id]
		if not (data and data.grantedEffect.support) then fail("INVALID_REQUEST", "К умению можно добавить только камни поддержки") end
		local index = input.sourceIndex and input.sourceIndex - offset
		if input.sourceIndex == 1 then fail("INVALID_REQUEST", "Умение от предмета нельзя заменить") end
		if not index then added[#added + 1] = data.grantedEffect end
		node[#node + 1] = replacementGem(input, previous and previous[index], target and target.gemList[index], used)
	end
	if target or #node > 0 then
		local replacement = loadGroup(node)
		if target then
			if scope == "skill" then replacement.gemList[1] = primary end
			target.gemList = replacement.gemList
			build.skillsTab:ProcessSocketGroup(target)
		else
			groups[#groups + 1] = replacement
		end
	end
	build.skillsTab:SetDisplayGroup(group)
	local result = finish()
	for _, effect in ipairs(added) do
		if not granted.canSupport(group, effect) then fail("INVALID_REQUEST", "Эта поддержка не подходит выбранному умению") end
	end
	result.groupId = params.groupId
	return result
end
function methods.updateSkillGroup(params)
	local groups = build.skillsTab.socketGroupList
	local old = groups[params.groupId]
	if not old then fail("INVALID_REQUEST", "Группа не найдена") end
	if type(params.gems) ~= "table" or #params.gems < 1 or #params.gems > 12 then fail("INVALID_REQUEST", "Нужен список из 1–12 камней") end
	local scope = granted.scope(build, old)
	if scope == "none" then fail("INVALID_REQUEST", "Для этого умения нельзя добавить поддержки") end
	if scope then return updateGranted(old, params, scope) end
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
	local replacement = loadGroup(node)
	groups[params.groupId] = replacement
	build.skillsTab:SetDisplayGroup(replacement)
	local result = finish()
	result.groupId = params.groupId
	return result
end
function methods.deleteSkillGroup(params)
	local groups = build.skillsTab.socketGroupList
	local group = groups[params.groupId]
	if not group then fail("INVALID_REQUEST", "Группа не найдена") end
	if group.source then fail("INVALID_REQUEST", "Группа создана предметом; измените источник умения") end
	local count = #groups
	local control = build.skillsTab.controls.groupList
	local previousConfirm = rawget(main, "OpenConfirmPopup")
	-- API уже содержит явное намерение удалить; выполняется только исходное подтверждение этой операции.
	main.OpenConfirmPopup = function(_, title, message, button, callback)
		if title ~= "Delete Socket Group" or type(callback) ~= "function" then fail("INVALID_REQUEST", "Неожиданный диалог удаления") end
		callback()
	end
	local ok, problem = pcall(function()
		control.selIndex, control.selValue = params.groupId, group
		control:OnSelDelete(params.groupId, group)
	end)
	main.OpenConfirmPopup = previousConfirm
	if not ok then error(problem, 0) end
	if #groups ~= count - 1 then fail("CALCULATION_FAILED", "Исходный PoB не удалил группу") end
	return finish()
end
end
