-- Каталог и совместимость используют данные и проверку исходного PoB.
return function(methods, fail)
local assets
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
	for index, gem in ipairs(group.gemList) do
		local support = gem.gemData and gem.gemData.grantedEffect.support
		if (index == 1 and support) or (index > 1 and not support) then
			fail("INVALID_REQUEST", "Сначала нужен камень умения, затем камни поддержки")
		end
	end
	local result = {}
	for id, gem in pairs(build.data.gems) do
		if gem.grantedEffect and gem.grantedEffect.support then
			for _, activeSkill in ipairs(group.displaySkillList or {}) do
				if calcLib.canGrantedEffectSupportActiveSkill(gem.grantedEffect, activeSkill) then
					result[#result + 1] = id
					break
				end
			end
		end
	end
	table.sort(result)
	return { source = "original-lua", supportIds = result }
end
end
