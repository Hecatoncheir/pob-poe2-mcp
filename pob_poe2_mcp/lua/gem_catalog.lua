-- Каталог и совместимость используют данные и проверку исходного PoB.
return function(methods, fail, granted)
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
end
