-- API ассистентов: игровые операции выполняют исходные классы Lua.
return function(methods, fail, snapshot, finish)
	local function integer(value, low, high)
		return type(value) == "number" and value % 1 == 0 and value >= low and value <= high
	end
	local function clean(text)
		return tostring(text or ""):gsub("%^x%x%x%x%x%x%x", ""):gsub("%^%d", "")
	end
	local function scalars(source)
		local result = {}
		for key, value in pairs(source or {}) do
			if type(key) == "string" and (type(value) == "string" or type(value) == "boolean") then result[key] = value
			elseif type(key) == "string" and type(value) == "number" then
				if value == value and math.abs(value) ~= math.huge then result[key] = value end
			end
		end
		return result
	end
	local function attributeOptions(node)
		if not node.isAttribute then return nil end
		local result = {}
		for index, option in ipairs(node.options or {}) do
			result[index] = { id = option.id, name = clean(option.dn or option.name), stats = option.sd or option.stats }
		end
		return result
	end
	function methods.createBuild(params)
		if not integer(params.level or 1, 1, 100) then fail("INVALID_REQUEST", "Уровень должен быть целым от 1 до 100") end
		if params.classId ~= nil and not build.spec.tree.classes[params.classId] then fail("INVALID_REQUEST", "Класс не найден") end
		if params.name ~= nil and (type(params.name) ~= "string" or #params.name > 200) then fail("INVALID_REQUEST", "Некорректное название") end
		newBuild()
		build.buildName = params.name or "Assistant build"
		if params.classId ~= nil then build.spec:SelectClass(params.classId) end
		build.controls.characterLevel:SetText(tostring(params.level or 1), true)
		return finish()
	end
	function methods.getCatalog(params)
		local kind = params.kind or "gems"
		local query = type(params.query) == "string" and params.query:lower() or ""
		local limit, offset = params.limit or 50, params.offset or 0
		if not integer(limit, 1, 200) or not integer(offset, 0, 100000) then fail("INVALID_REQUEST", "Некорректная страница") end
		local entries = {}
		local function add(entry)
			local search = tostring(entry.id) .. " " .. (entry.name or "")
			for _, stat in ipairs(entry.stats or {}) do search = search .. " " .. stat end
			for _, option in ipairs(entry.attributeOptions or {}) do search = search .. " " .. option.name end
			if search:lower():find(query, 1, true) then entries[#entries + 1] = entry end
		end
		if kind == "gems" then
			for id, gem in pairs(build.data.gems) do add({ id = id, name = gem.name, skillId = gem.grantedEffectId, support = gem.support == true, naturalMaxLevel = gem.naturalMaxLevel }) end
		elseif kind == "classes" then
			for id, class in pairs(build.spec.tree.classes) do
				local asc = {}
				for ascId, value in pairs(class.classes) do asc[#asc + 1] = { id = ascId, name = value.name } end
				add({ id = id, name = class.name, ascendancies = asc })
			end
		elseif kind == "nodes" then
			for id, node in pairs(build.spec.nodes) do add({ id = id, name = node.dn, type = node.type, stats = node.sd, attributeOptions = attributeOptions(node), masteryEffects = node.masteryEffects, allocated = node.alloc == true, points = node.pathDist, path = (function() local out = {}; for _, n in ipairs(node.path or {}) do out[#out + 1] = n.id end; return out end)() }) end
		elseif kind == "config" then
			for _, value in ipairs(require("Modules.ConfigOptions")) do
				if value.var then
					local choices = {}
					for _, choice in ipairs(value.list or {}) do choices[#choices + 1] = { value = choice.val, label = clean(choice.label) } end
					add({ id = value.var, name = clean(value.label), type = value.type, choices = choices })
				end
			end
		elseif kind == "bases" then
			for name, base in pairs(build.data.itemBases) do add({ id = name, name = name, type = base.type, requirements = scalars(base.req) }) end
		elseif kind == "slots" then
			for _, slot in ipairs(build.itemsTab.orderedSlots) do if not slot.nodeId then add({ id = slot.slotName, name = slot.slotName }) end end
		else fail("INVALID_REQUEST", "Неизвестный каталог") end
		table.sort(entries, function(a, b) return tostring(a.id) < tostring(b.id) end)
		local page = {}
		for index = offset + 1, math.min(#entries, offset + limit) do page[#page + 1] = entries[index] end
		return { kind = kind, entries = page, total = #entries, offset = offset, limit = limit }
	end
	function methods.addSkillGroup(params)
		if type(params.gems) ~= "table" or #params.gems < 1 or #params.gems > 12 then fail("INVALID_REQUEST", "Нужен список из 1–12 камней") end
		local node = { elem = "Skill", attrib = { enabled = "true", includeInFullDPS = "true", label = params.label or "", mainActiveSkill = "1" } }
		if type(node.attrib.label) ~= "string" or #node.attrib.label > 200 then fail("INVALID_REQUEST", "Некорректная метка") end
		for _, input in ipairs(params.gems) do
			if type(input) ~= "table" or not build.data.gems[input.id] then fail("INVALID_REQUEST", "Неизвестный ID камня; используйте getCatalog") end
			if not integer(input.level or 1, 1, 40) or not integer(input.quality or 0, 0, 100) then fail("INVALID_REQUEST", "Некорректный уровень или качество камня") end
			local gem = build.data.gems[input.id]
			node[#node + 1] = { elem = "Gem", attrib = { skillId = gem.grantedEffectId, nameSpec = gem.name, level = tostring(input.level or 1), quality = tostring(input.quality or 0), enabled = tostring(input.enabled ~= false) } }
		end
		build.skillsTab:LoadSkill(node, build.skillsTab.activeSkillSetId)
		local group = build.skillsTab.socketGroupList[#build.skillsTab.socketGroupList]
		build.skillsTab:SetDisplayGroup(group)
		local result = finish()
		result.groupId = #build.skillsTab.socketGroupList
		return result
	end
	function methods.addItem(params)
		if type(params.raw) ~= "string" or #params.raw > 65536 then fail("INVALID_REQUEST", "Некорректный текст предмета") end
		local item = new("Item"):Item(params.raw)
		if not item.base then fail("INVALID_REQUEST", "Lua не распознал базу предмета") end
		local slot = params.slot and build.itemsTab.slots[params.slot]
		if params.slot and (not slot or slot.nodeId or not build.itemsTab:IsItemValidForSlot(item, params.slot)) then fail("INVALID_REQUEST", "Предмет несовместим со слотом") end
		build.itemsTab:AddItem(item, true)
		if slot then slot:SetSelItemId(item.id) end
		build.itemsTab:PopulateSlots()
		build.itemsTab:UpdateSockets()
		local result = finish()
		result.itemId = item.id
		return result
	end
	function methods.setConfig(params)
		if type(params.values) ~= "table" then fail("INVALID_REQUEST", "Нужен объект values") end
		local definitions = {}
		for _, value in ipairs(require("Modules.ConfigOptions")) do if value.var then definitions[value.var] = value end end
		for key, value in pairs(params.values) do
			local def = definitions[key]
			if not def then fail("INVALID_REQUEST", "Неизвестная настройка: " .. tostring(key)) end
			local valid = def.type == "check" and type(value) == "boolean"
				or (def.type == "count" or def.type == "integer" or def.type == "countAllowZero" or def.type == "float") and type(value) == "number" and value == value and math.abs(value) < 1000000000
				or def.type == "text" and type(value) == "string" and #value <= 65536
			if def.type == "list" then for _, choice in ipairs(def.list or {}) do if choice.val == value then valid = true end end end
			if type(value) == "number" and def.type ~= "list" and def.type ~= "float" and value % 1 ~= 0 then valid = false end
			if not valid then fail("INVALID_REQUEST", "Недопустимое значение: " .. key) end
			build.configTab.input[key] = value
		end
		build.configTab:BuildModList()
		return finish()
	end
	function methods.getBuildReport()
		local groups, items, slots, warnings = {}, {}, {}, {}
		for id, group in ipairs(build.skillsTab.socketGroupList) do
			local gems = {}
			for _, gem in ipairs(group.gemList) do gems[#gems + 1] = { id = gem.gemId, skillId = gem.skillId, name = gem.nameSpec, level = gem.level, quality = gem.quality, enabled = gem.enabled, error = gem.errMsg } end
			groups[#groups + 1] = { id = id, label = clean(group.displayLabel), enabled = group.enabled, gems = gems }
		end
		for id, item in pairs(build.itemsTab.items) do
			local unsupported = {}
			for _, list in ipairs({ item.implicitModLines or {}, item.explicitModLines or {}, item.enchantModLines or {}, item.buffModLines or {} }) do
				for _, line in ipairs(list) do if line.extra or not line.modList or #line.modList == 0 then unsupported[#unsupported + 1] = { line = line.line, extra = line.extra } end end
			end
			items[#items + 1] = { id = id, name = item.title or item.name, base = item.baseName, rarity = item.rarity, raw = item.raw, unsupported = unsupported }
		end
		table.sort(items, function(a, b) return a.id < b.id end)
		for _, slot in ipairs(build.itemsTab.orderedSlots) do slots[#slots + 1] = { name = slot.slotName, itemId = slot.selItemId, active = slot.active } end
		for _, line in ipairs(build.controls.warnings.lines or {}) do warnings[#warnings + 1] = clean(line) end
		local allocated = {}
		for id in pairs(build.spec.allocNodes) do allocated[#allocated + 1] = id end
		table.sort(allocated)
		local customMods = {}
		local function addCustom(title, text, enabled)
			if not text or text == "" then return end
			local unparsed = {}
			for line in text:gmatch("[^\r\n]+") do
				if line:match("%S") then
					local mods, extra = modLib.parseMod(line)
					if not mods or extra then unparsed[#unparsed + 1] = { line = line, extra = extra } end
				end
			end
			customMods[#customMods + 1] = { title = title, text = text, enabled = enabled, unparsed = unparsed }
		end
		addCustom("input.customMods", build.configTab.input.customMods, true)
		local activeConfig = build.configTab.configSets[build.configTab.activeConfigSetId]
		for _, block in ipairs(activeConfig.customModsList or {}) do addCustom(block.title, block.text, block.enabled) end
		local sets = {}
		for kind, source in pairs({ tree = build.treeTab.specList, skills = build.skillsTab.skillSets, items = build.itemsTab.itemSets, config = build.configTab.configSets }) do
			sets[kind] = {}
			for id, value in pairs(source or {}) do sets[kind][#sets[kind] + 1] = { id = id, title = value.title } end
			table.sort(sets[kind], function(a, b) return a.id < b.id end)
		end
		return { source = "original-lua", snapshot = snapshot(), stats = scalars(build.calcsTab.mainOutput), config = scalars(build.configTab.input), configPlaceholders = scalars(build.configTab.placeholder), groups = groups, items = items, slots = slots, warnings = warnings, allocatedNodes = allocated, pointDisplay = clean(build.controls.pointDisplay.str), notes = build.notesTab.controls.edit.buf,
			customMods = customMods, sets = sets, activeSets = { tree = build.treeTab.activeSpec, skills = build.skillsTab.activeSkillSetId, items = build.itemsTab.activeItemSetId, config = build.configTab.activeConfigSetId },
			validationScope = "Lua calculation and exposed warnings; not a guarantee of in-game legality or performance" }
	end
end
