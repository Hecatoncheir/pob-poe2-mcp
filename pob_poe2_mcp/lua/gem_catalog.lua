-- Каталог и совместимость используют данные и проверку исходного PoB.
return function(methods, fail, granted, canPreview)
local assets
local gemTooltip
local function tooltipInstance(params)
	if params.groupId ~= nil or params.sourceIndex ~= nil then
		if params.id ~= nil or params.level ~= nil or params.quality ~= nil then fail("INVALID_REQUEST", "Укажите камень группы либо отдельный ID с уровнем и качеством") end
		local group = build.skillsTab.socketGroupList[params.groupId]
		local instance = group and granted.gems(build, group)[params.sourceIndex]
		if not instance or not instance.gemData then fail("INVALID_REQUEST", "Камень группы не найден") end
		local result = {}
		for key, value in pairs(instance) do result[key] = value end
		return result
	end
	local gem = build.data.gems[params.id]
	if not gem or not gem.grantedEffect then fail("INVALID_REQUEST", "Неизвестный ID камня") end
	return { gemData = gem, gemId = params.id, nameSpec = gem.name, skillId = gem.grantedEffectId,
		level = params.level or 1, quality = params.quality or 0, count = 1,
		enabled = true, enableGlobal1 = true, enableGlobal2 = true, corruptLevel = 0, corrupted = false }
end
function methods.getGemTooltip(params)
	local instance = tooltipInstance(params)
	local collector = { lines = {} }
	function collector:AddLine(size, text)
		if type(text) == "string" and text:match("%S") then
			text = text:gsub("^(%^x%x%x%x%x%x%x)%s+", "%1"):gsub("^%s+", "")
			self.lines[#self.lines + 1] = { size = size, text = text }
		end
	end
	function collector:AddSeparator()
		if #self.lines > 0 and not self.lines[#self.lines].separator then self.lines[#self.lines + 1] = { separator = true } end
	end
	gemTooltip = gemTooltip or LoadModule("Classes/GemTooltip")
	gemTooltip.AddGemTooltip(collector, build, instance)
	if collector.lines[#collector.lines] and collector.lines[#collector.lines].separator then table.remove(collector.lines) end
	return { source = "original-lua", lines = collector.lines }
end
local function iconAsset(gem)
	if not assets then
		assets = {}
		for file, coordinates in pairs(build.data.skillAssets.ddsCoords or {}) do
			if file:match("^gem%-icons_") then
				for name, index in pairs(coordinates) do
					assets[name] = { file = "Data/Skills/" .. file, index = index }
				end
			end
		end
	end
	return gem.grantedEffect and assets[gem.grantedEffect.icon]
end
function methods.getGemIconAssets(params)
	local result = {}
	for _, id in ipairs(params.ids or {}) do
		local gem = build.data.gems[id]
		if not gem then fail("INVALID_REQUEST", "Неизвестный ID камня") end
		local asset = iconAsset(gem)
		result[#result + 1] = asset and { id = id, file = asset.file, index = asset.index } or { id = id, error = "В исходном PoB нет иконки этого камня" }
	end
	return { icons = result }
end
function methods.getCompatibleSupports(params)
	local group = build.skillsTab.socketGroupList[params.groupId]
	if not group then fail("INVALID_REQUEST", "Группа не найдена") end
	for index, gem in ipairs(granted.gems(build, group)) do
		local support = gem.gemData and gem.gemData.grantedEffect.support
		if (index == 1 and support) or (index > 1 and not support) then
			fail("INVALID_REQUEST", "Сначала нужен камень умения, затем камни поддержки")
		end
	end
	local result = {}
	for id, gem in pairs(build.data.gems) do
		if gem.grantedEffect and gem.grantedEffect.support and granted.canSupport(group, gem.grantedEffect) then
			result[#result + 1] = id
		end
	end
	table.sort(result)
	return { source = "original-lua", supportIds = result }
end

if not canPreview then return end

local function matchingSkill(group, target, effectId)
	local first
	for index, skill in ipairs(group.displaySkillList or {}) do
		local effect = skill.activeEffect
		if effect.srcInstance == target and (not effectId or effect.grantedEffect.id == effectId) then
			if index == group.mainActiveSkill then return index end
			first = first or index
		end
	end
	return first
end

function methods.measureSupportPreview(params)
	local group = build.skillsTab.socketGroupList[params.groupId]
	if not group or not group.enabled then fail("INVALID_REQUEST", "Группа умений выключена или недоступна") end
	if build.mainSocketGroup ~= params.groupId then
		methods.selectMainSkill({ control = "groups", id = params.groupId })
	end
	local target = granted.gems(build, group)[params.targetIndex]
	if target and target.gemData and target.gemData.grantedEffect.support then
		fail("INVALID_REQUEST", "Для расчёта нужен активный камень")
	end
	local index = target and target.enabled and matchingSkill(group, target, params.effectId)
	if not index then fail("INVALID_REQUEST", "Выбранное умение недоступно для расчёта") end
	local expectedEffect = group.displaySkillList[index].activeEffect.grantedEffect.id
	if group.mainActiveSkill ~= index then
		methods.selectMainSkill({ control = "skills", id = index })
	end
	local skill = build.calcsTab.mainEnv.player.mainSkill
	local effect = skill.activeEffect
	if effect.srcInstance ~= target or effect.grantedEffect.id ~= expectedEffect then
		fail("CALCULATION_FAILED", "Lua выбрал другое умение")
	end

	if params.supportId then
		local gem = build.data.gems[params.supportId]
		local support = gem and gem.grantedEffect
		if not support or not support.support or not calcLib.canGrantedEffectSupportActiveSkill(support, skill) then
			fail("INVALID_REQUEST", "Эта поддержка не подходит выбранному умению")
		end
	end
	return { dps = methods.getSnapshot().output.TotalDPS, effectId = effect.grantedEffect.id,
		part = target.skillPart or 1, statSet = effect.statSet and effect.statSet.index or 1 }
end
end
