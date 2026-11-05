-- Общая сессия API: расчёты и изменения выполняют оригинальные классы PoB.
return function(host, packageDir)
local environment = setmetatable({ build = host.get_build(), POB_MCP_PACKAGE_DIR = packageDir }, { __index = _G })
-- Отдельное окружение не подменяет глобальное состояние графического приложения.
setfenv(1, environment)
local json = require("dkjson")
function construct(className, ...)
	if not common.classes[className] then LoadModule("Classes/" .. className) end
	if common.classes[className][className] then
		local object = new(className)
		return object[className](object, ...)
	end
	return new(className, ...)
end
local function runCallback() return host.frame() end
local function newBuild()
	host.new_build()
	environment.build = host.get_build()
end
local function loadBuildFromXML(xml, name)
	host.load_build(xml, name)
	environment.build = host.get_build()
end
environment.newBuild = newBuild
environment.loadBuildFromXML = loadBuildFromXML
local revision = 0
local loaded = host.live == true
local running = true
local function fail(code, message)
	error({ code = code, message = message, recoverable = true }, 0)
end
local function selector(control)
	local entries = {}
	for index, value in ipairs(control.list or {}) do
		local label = type(value) == "table" and value.label or value
		entries[#entries + 1] = { id = index, label = tostring(label):gsub("%^x%x%x%x%x%x%x", ""):gsub("%^%d", "") }
	end
	return { entries = entries, selected = control.selIndex, enabled = control:IsShown() and control:IsEnabled() }
end
local function snapshot()
	local values = {}
	for _, name in ipairs({ "TotalDPS", "Life", "Mana", "EnergyShield", "Spirit", "FireResist", "ColdResist", "LightningResist", "ChaosResist" }) do
		local value = build.calcsTab.mainOutput[name]
		if value ~= nil then
			if type(value) ~= "number" or value ~= value or math.abs(value) == math.huge then
				fail("CALCULATION_FAILED", "Некорректный показатель: " .. name)
			end
			values[name] = value
		end
	end
	return { targetVersion = build.targetVersion, treeVersion = build.spec.treeVersion, output = values,
		buildInfo = { name = build.buildName, level = build.characterLevel, class = build.spec.curClassName,
			ascendancy = build.spec.curAscendClassName, groups = selector(build.controls.mainSocketGroup),
			skills = selector(build.controls.mainSkill) } }
end
local function validateXML(xml)
	if type(xml) ~= "string" or #xml > 4 * 1024 * 1024 then
		fail("INVALID_BUILD", "XML отсутствует или превышает лимит")
	end
	local parsed = common.xml.ParseXML(xml)
	if not parsed or not parsed[1] or parsed[1].elem ~= "PathOfBuilding2" then
		fail("INVALID_BUILD", "Ожидалась сборка PathOfBuilding2")
	end
end
local methods = {}
local function nodeIds(nodes)
	local ids = {}
	for _, node in ipairs(nodes or {}) do ids[#ids + 1] = node.id end
	return ids
end
local function getNode(id)
	local node = build.spec.nodes[id]
	if not node then fail("INVALID_REQUEST", "Узел не найден") end
	return node
end
local function finishTreeChange()
	build.buildFlag = true
	runCallback("OnFrame")
	return snapshot()
end
function methods.getNodeTooltip(params)
	local node = getNode(params.id)
	local collector = { lines = {} }
	function collector:AddLine(size, text) self.lines[#self.lines + 1] = { size = size, text = text } end
	function collector:AddSeparator() self.lines[#self.lines + 1] = { separator = true } end
	function collector:SetRecipe(recipe)
		self.recipe = {}
		for _, ingredient in ipairs(recipe or {}) do self.recipe[#self.recipe + 1] = ingredient.name end
	end
	function collector:AddBuildPlannerNote(size, text, prefix) self:AddLine(size, (prefix or "") .. text) end
	local viewer = build.treeTab.viewer
	viewer.skillTooltip:Clear()
	local previous = viewer.showStatDifferences
	viewer.showStatDifferences = params.compare ~= false
	local increasedEffect = 0
	for _, allocated in pairs(build.spec.allocNodes) do increasedEffect = increasedEffect + allocated.modList:Sum("INC", nil, "SmallPassiveSkillEffect") end
	local ok, message = pcall(viewer.AddNodeTooltip, viewer, collector, node, build, increasedEffect)
	viewer.showStatDifferences = previous
	if not ok then fail("CALCULATION_FAILED", tostring(message)) end
	if #viewer.skillTooltip.lines > 0 then
		collector:AddSeparator()
		for _, line in ipairs(viewer.skillTooltip.lines) do
			if line.text then collector:AddLine(line.size, line.text) else collector:AddSeparator() end
		end
	end
	return { lines = collector.lines, recipe = collector.recipe, path = nodeIds(node.alloc and node.depends or node.path), points = node.pathDist, note = build.spec.nodeNotes and build.spec.nodeNotes[node.id] }
end
function methods.treeAction(params)
	local node = getNode(params.id)
	local spec = build.spec
	if params.action == "jewel" then
		local slot = build.itemsTab:GetSocketAndJewelForNodeID(node.id)
		if not slot or not node.alloc then fail("INVALID_REQUEST", "Сначала назначьте гнездо самоцвета") end
		local itemId = params.item or 0
		if params.raw then
			if type(params.raw) ~= "string" or #params.raw > 65536 then fail("INVALID_REQUEST", "Некорректный текст самоцвета") end
			local item = construct("Item", params.raw)
			if not item.base or not build.itemsTab:IsItemValidForSlot(item, slot.slotName) then fail("INVALID_REQUEST", "Этот предмет не подходит к гнезду") end
			build.itemsTab:AddItem(item, true)
			itemId = item.id
		end
		local item = build.itemsTab.items[itemId]
		if itemId ~= 0 and (not item or not build.itemsTab:IsItemValidForSlot(item, slot.slotName)) then fail("INVALID_REQUEST", "Самоцвет не подходит к гнезду") end
		slot:SetSelItemId(itemId)
		build.itemsTab:PopulateSlots()
		build.itemsTab:UpdateSockets()
		return finishTreeChange()
	end
	if params.action == "note" then
		if type(params.text) ~= "string" or #params.text > 65536 then fail("INVALID_REQUEST", "Некорректная заметка") end
		if not spec.nodeNotes then fail("UNSUPPORTED_OPERATION", "Эта версия PoB не поддерживает заметки узлов") end
		spec.nodeNotes[node.id] = params.text ~= "" and params.text or nil
		return finishTreeChange()
	end
	if node.type == "ClassStart" or node.type == "AscendClassStart" or node.type == "OnlyImage" then fail("INVALID_REQUEST", "Выберите доступное умение") end
	if node.unlockConstraint and not build.treeTab.viewer:checkUnlockConstraints(build, node) then fail("INVALID_REQUEST", "Условия доступа к узлу не выполнены") end
	local globalNode = node.type == "Keystone" or node.type == "Socket" or node.containJewelSocket
	if globalNode and spec.allocMode > 0 and (not node.alloc or node.allocMode == 0) then fail("INVALID_REQUEST", "Глобальные узлы изменяются в основном дереве") end
	if globalNode and not node.alloc and build.treeTab.viewer:IsConnectedToWeaponSetNodes(node) then fail("INVALID_REQUEST", "Глобальному узлу нужен путь через основное дерево") end
	if params.attribute ~= nil then
		if params.attribute ~= 1 and params.attribute ~= 2 and params.attribute ~= 3 then fail("INVALID_REQUEST", "Некорректный атрибут") end
		spec.attributeIndex = params.attribute
	end
	if params.action == "refund" or (params.action == "toggle" and node.alloc and not params.attribute) then
		spec:DeallocNode(node)
		return finishTreeChange()
	end
	if params.action ~= "allocate" and params.action ~= "toggle" and params.action ~= "right" then fail("INVALID_REQUEST", "Неизвестное действие дерева") end
	if not node.alloc and (not node.path or #node.path == 0) then fail("INVALID_REQUEST", "Нет доступного пути к узлу") end
	if node.isAttribute then
		local index = params.attribute or spec.attributeIndex or 1
		if params.action == "right" and node.alloc and not params.attribute then
			local nextIndex = { Strength = 2, Dexterity = 3, Intelligence = 1 }
			index = nextIndex[node.dn] or index
		end
		spec.attributeIndex = index
		spec:SwitchAttributeNode(node.id, index)
	end
	if node.type == "Mastery" then
		local effect = spec.tree.masteryEffects[params.mastery]
		local valid = false
		for _, option in ipairs(node.masteryEffects or {}) do if option.effect == params.mastery then valid = true end end
		if not effect or not valid then fail("INVALID_REQUEST", "Выберите эффект мастерства") end
		for otherId, selected in pairs(spec.masterySelections) do
			if selected == effect.id and otherId ~= node.id then fail("INVALID_REQUEST", "Этот эффект уже выбран") end
		end
		node.sd = effect.sd
		node.allMasteryOptions = false
		spec.tree:ProcessStats(node)
		spec.masterySelections[node.id] = effect.id
	end
	local path
	if params.path then
		path = {}
		local last
		for _, id in ipairs(params.path) do
			local current = getNode(id)
			if last and not isValueInArray(last.linked, current) then fail("INVALID_REQUEST", "Путь содержит несвязанные узлы") end
			path[#path + 1], last = current, current
		end
		if #path == 0 or path[#path] ~= node or not path[1].alloc then fail("INVALID_REQUEST", "Путь должен начинаться на назначенном узле и заканчиваться на выбранном") end
	end
	spec:AllocNode(node, path)
	spec:BuildAllDependsAndPaths()
	return finishTreeChange()
end
function methods.getJewels(params)
	local node = getNode(params.id)
	local slot = build.itemsTab:GetSocketAndJewelForNodeID(node.id)
	if not slot then fail("INVALID_REQUEST", "Гнездо не найдено") end
	local items = {}
	for id, item in pairs(build.itemsTab.items) do
		if build.itemsTab:IsItemValidForSlot(item, slot.slotName) then items[#items + 1] = { id = id, name = item.name or item.title or item.baseName, raw = item:BuildRaw() } end
	end
	return { items = items, selected = slot.selItemId }
end
function methods.treeOptions(params)
	local spec = build.spec
	if params.specAction then
		local tab = build.treeTab
		if params.specAction == "rename" then
			if type(params.name) ~= "string" or #params.name == 0 or #params.name > 200 then fail("INVALID_REQUEST", "Некорректное имя набора") end
			spec.title = params.name
		elseif params.specAction == "clone" or params.specAction == "new" then
			if type(params.name) ~= "string" or #params.name == 0 or #params.name > 200 then fail("INVALID_REQUEST", "Некорректное имя набора") end
			local created = construct("PassiveSpec", build, spec.treeVersion)
			if params.specAction == "clone" then
				created:RestoreUndoState(spec:CreateUndoState())
				created.jewels = copyTable(spec.jewels)
			else created:SelectClass(spec.curClassId) end
			created.title = params.name
			table.insert(tab.specList, created)
			tab:SetActiveSpec(#tab.specList)
		elseif params.specAction == "delete" then
			if #tab.specList < 2 then fail("INVALID_REQUEST", "Нельзя удалить последний набор") end
			table.remove(tab.specList, tab.activeSpec)
			tab:SetActiveSpec(math.min(tab.activeSpec, #tab.specList))
		else fail("INVALID_REQUEST", "Неизвестное действие набора") end
	end
	if params.compare ~= nil then
		local tab = build.treeTab
		if params.compare ~= 0 and not tab.specList[params.compare] then fail("INVALID_REQUEST", "Набор сравнения не найден") end
		tab.controls.compareCheck.state = params.compare ~= 0
		tab.isComparing = params.compare ~= 0
		if params.compare ~= 0 then tab:SetCompareSpec(params.compare) end
		tab.viewer.compareSpec = params.compare ~= 0 and tab.compareSpec or nil
	end
	if params.mode ~= nil then
		if params.mode ~= 0 and params.mode ~= 1 and params.mode ~= 2 then fail("INVALID_REQUEST", "Неизвестный оружейный режим") end
		spec.allocMode = params.mode
	end
	if params.class ~= nil then
		if not spec.tree.classes[params.class] then fail("INVALID_REQUEST", "Класс не найден") end
		if spec:CountAllocNodes() > 0 and not spec:IsClassConnected(params.class) then
			if params.connect then
				if not spec:ConnectToClass(params.class) then fail("INVALID_REQUEST", "Не удалось соединить класс") end
			elseif not params.reset then fail("INVALID_REQUEST", "Смена класса требует соединения или сброса дерева") end
		end
		if params.reset then wipeTable(spec.hashOverrides); spec:ResetNodes() end
		spec:SelectClass(params.class)
	end
	if params.ascendancy ~= nil then
		if not spec.curClass.classes[params.ascendancy] then fail("INVALID_REQUEST", "Восхождение недоступно для класса") end
		spec:SelectAscendClass(params.ascendancy)
	end
	if params.reset and not params.class then wipeTable(spec.hashOverrides); spec:ResetNodes() end
	if params.spec ~= nil then
		if not build.treeTab.specList[params.spec] then fail("INVALID_REQUEST", "Набор дерева не найден") end
		build.treeTab:SetActiveSpec(params.spec)
	end
	build.spec:BuildAllDependsAndPaths()
	return finishTreeChange()
end
function methods.getTree()
	local nodes, edges = {}, {}
	for id, node in pairs(build.spec.nodes) do
		if type(node.x) == "number" and type(node.y) == "number" then
			nodes[#nodes + 1] = { id = id, x = node.x, y = node.y, name = node.dn or node.name or "", type = node.type, icon = node.icon, allocated = node.alloc == true, stats = node.sd or {}, targetSize = node.targetSize, overlay = node.overlay, effect = node.activeEffectImage, isAttribute = node.isAttribute == true, path = nodeIds(node.path), depends = nodeIds(node.depends), points = node.pathDist, allocMode = node.allocMode, masteryEffects = node.masteryEffects, note = build.spec.nodeNotes and build.spec.nodeNotes[id], ascendancy = node.ascendancyName }
			local exported = nodes[#nodes]
			local compared = build.treeTab.viewer.compareSpec
			exported.compareAllocated = compared and compared.allocNodes[id] ~= nil
			exported.compareMode = compared and compared.nodes[id] and compared.nodes[id].allocMode
			local _, jewel = build.itemsTab:GetSocketAndJewelForNodeID(id)
			if jewel and node.alloc then
				exported.jewel = artManifest[jewel.title] and jewel.title or jewel.baseName
				if jewel.jewelRadiusIndex and not node.noRadius then
					local radius = build.data.jewelRadius[jewel.jewelRadiusIndex]
					local multiplier = data.gameConstants.PassiveTreeJewelDistanceMultiplier
					exported.radius = { outer = radius.outer * multiplier, inner = radius.inner * multiplier }
				end
			end
			for _, other in ipairs(node.linked or {}) do
				if id < other.id then edges[#edges + 1] = { id, other.id } end
			end
		end
	end
	-- Устойчивый порядок отрисовки перекрывающихся узлов.
	table.sort(nodes, function(a, b) return a.id < b.id end)
	local backgrounds = {}
	local function addBackground(data, brightness, rotation)
		backgrounds[#backgrounds + 1] = { image = data.image, x = data.x, y = data.y, width = data.width * 2, height = data.height * 2, brightness = brightness or 1, rotation = rotation or 0 }
	end
	for _, character in pairs(build.spec.tree.classes) do
		if character.name == build.spec.curClassName and character.background then
			local bg = character.background
			local selectedAscendancy = character.classes[build.spec.curAscendClassId]
			local portrait = selectedAscendancy and selectedAscendancy.background and selectedAscendancy.background.image or bg.image
			addBackground({ image = portrait, x = bg.x, y = bg.y, width = bg.width, height = bg.height })
			local start = build.spec.nodes[character.startNodeId]
			addBackground({ image = "BGTreeActive", x = bg.x, y = bg.y, width = bg.active.width, height = bg.active.height }, 1, math.pi / 2 + math.atan2(start.y - bg.y, start.x - bg.x))
			addBackground({ image = "BGTree", x = bg.x, y = bg.y, width = bg.bg.width, height = bg.bg.height })
		end
		for _, asc in pairs(character.ascendancies or {}) do
			if asc.background then addBackground(asc.background, asc.name == build.spec.curAscendClassBaseName and 1 or 0.5) end
		end
	end
	for _, group in pairs(build.spec.tree.groups) do
		if group.background and not group.isProxy then
			local bg = group.background
			local asset = artManifest[bg.image]
			if asset then
				addBackground({ image = bg.image, x = group.x + (bg.offsetX or 0), y = group.y + (bg.offsetY or 0), width = asset.width, height = asset.height })
				backgrounds[#backgrounds].half = bg.isHalfImage ~= nil
			end
		end
	end
	local connectors = {}
	local sourceConnectors = {}
	for _, connector in ipairs(build.spec.tree.connectors) do sourceConnectors[#sourceConnectors + 1] = connector end
	for _, graph in pairs(build.spec.subGraphs) do
		for _, connector in ipairs(graph.connectors) do sourceConnectors[#sourceConnectors + 1] = connector end
	end
	for _, connector in ipairs(sourceConnectors) do
		local vertices = {}
		for state, points in pairs(connector.vert) do vertices[state] = { unpack(points, 1, 8) } end
		connectors[#connectors + 1] = { a = connector.nodeId1, b = connector.nodeId2, vertices = vertices, uv = { unpack(connector.c, 9, 16) }, assets = connector.assetNames }
	end
	table.sort(connectors, function(a, b)
		if a.a == b.a then return a.b < b.b end
		return a.a < b.a
	end)
	local classes, specs = {}, {}
	for id, class in pairs(build.spec.tree.classes) do
		local ascendancies = {}
		for ascId, asc in pairs(class.classes) do ascendancies[#ascendancies + 1] = { id = ascId, name = asc.name } end
		classes[#classes + 1] = { id = id, name = class.name, ascendancies = ascendancies }
	end
	for id, spec in ipairs(build.treeTab.specList) do specs[#specs + 1] = { id = id, name = spec.title or tostring(id) } end
	return { nodes = nodes, edges = edges, connectors = connectors, backgrounds = backgrounds, version = build.spec.treeVersion, classes = classes, specs = specs, activeSpec = build.treeTab.activeSpec, compareSpec = build.treeTab.viewer.compareSpec and build.treeTab.activeCompareSpec or 0, classId = build.spec.curClassId, ascendancyId = build.spec.curAscendClassId, mode = build.spec.allocMode, pointDisplay = build.controls.pointDisplay.str, warnings = build.controls.warnings.lines }
end
function methods.toggleNode(params)
	local node = build.spec.nodes[params.id]
	if not node or node.type == "ClassStart" or node.type == "AscendClassStart" or node.type == "Mastery" then
		fail("INVALID_REQUEST", "Узел недоступен для переключения")
	end
	if node.alloc then build.spec:DeallocNode(node)
	else
		if not node.path or #node.path == 0 then fail("INVALID_REQUEST", "Нет доступного пути к узлу") end
		build.spec:AllocNode(node)
	end
	build.buildFlag = true
	runCallback("OnFrame")
	return snapshot()
end
local installMethods = dofile(POB_MCP_PACKAGE_DIR .. "/lua/assistant_methods.lua")
setfenv(installMethods, getfenv(1))
installMethods(methods, fail, snapshot, finishTreeChange)
local installImageData = dofile(POB_MCP_PACKAGE_DIR .. "/lua/image_data.lua")
setfenv(installImageData, getfenv(1))
installImageData(methods)
local installNodePower = dofile(POB_MCP_PACKAGE_DIR .. "/lua/node_power.lua")
setfenv(installNodePower, getfenv(1))
installNodePower(methods, fail)
function methods.initialize()
	local system = jit.os == "OSX" and "macos" or jit.os:lower()
	return { methods = { "initialize", "createBuild", "getCatalog", "getBuildReport", "getBuildImageData", "getTreeGeometry", "getTreeIconAssets", "getTreeHover", "getNodePower", "addSkillGroup", "addItem", "setConfig", "loadBuild", "getSnapshot", "getWorkbench", "setCustomMods", "exportBuild", "selectMainSkill", "getTree", "getNodeTooltip", "getJewels", "treeOptions", "treeAction", "toggleNode", "shutdown" }, platform = host.live and "windows-app" or system .. "-engine" }
end
function methods.loadBuild(params)
	validateXML(params.xml)
	loadBuildFromXML(params.xml, "MCP session")
	if launch.promptMsg then fail("INVALID_BUILD", tostring(launch.promptMsg)) end
	local result = snapshot()
	loaded = true
	return result
end
function methods.getSnapshot()
	return snapshot()
end
function methods.setCustomMods(params)
	if type(params.text) ~= "string" or #params.text > 65536 then
		fail("INVALID_REQUEST", "Некорректный текст модификаторов")
	end
	build.configTab.input.customMods = params.text
	build.configTab:BuildModList()
	runCallback("OnFrame")
	return snapshot()
end
function methods.selectMainSkill(params)
	local control = params.control == "groups" and build.controls.mainSocketGroup
		or params.control == "skills" and build.controls.mainSkill
	if not control or type(params.id) ~= "number" or params.id % 1 ~= 0
		or not control.list[params.id] or not control:IsShown() or not control:IsEnabled() then
		fail("INVALID_REQUEST", "Выбор умения недоступен")
	end
	control:SetSel(control:ListIndexToDropIndex(params.id, 0))
	runCallback("OnFrame")
	return snapshot()
end
function methods.getWorkbench()
	local items, groups = {}, {}
	for id, item in pairs(build.itemsTab.items) do
		items[#items + 1] = { id = id, name = item.title or item.name or item.baseName,
			base = item.baseName, rarity = item.rarity }
	end
	table.sort(items, function(a, b) return a.id < b.id end)
	for id, group in ipairs(build.skillsTab.socketGroupList) do
		groups[#groups + 1] = { id = id, label = tostring(group.displayLabel):gsub("%^x%x%x%x%x%x%x", ""):gsub("%^%d", "") }
	end
	return { items = items, groups = groups, notes = build.notesTab.controls.edit.buf }
end
function methods.exportBuild()
	return { xml = assert(build:SaveDB("MCP session")) }
end
function methods.shutdown()
	running = false
	return { stopped = true }
end
local lastXML
local mutations = { createBuild = true, addSkillGroup = true, addItem = true, setConfig = true, selectMainSkill = true, loadBuild = true, setCustomMods = true, toggleNode = true, treeAction = true, treeOptions = true }
local function dispatch(request)
	if type(request) ~= "table" or type(request.id) ~= "string" or type(request.method) ~= "string" then
		fail("INVALID_REQUEST", "Неверная структура запроса")
	end
	if request.protocol ~= 1 then fail("UNSUPPORTED_PROTOCOL", "Поддерживается protocol=1") end
	local method = methods[request.method]
	if not method then fail("UNKNOWN_METHOD", "Неизвестная команда") end
	if host.live then
		environment.build = host.get_build()
		loaded = environment.build ~= nil
		if loaded then
			local current = build:SaveDB("MCP session")
			if lastXML and current ~= lastXML then revision = revision + 1 end
			lastXML = current
		end
		if request.method ~= "initialize" and not loaded then fail("APP_NOT_IN_BUILD", "Откройте сборку в окне PoB") end
		if (request.method == "createBuild" or request.method == "loadBuild") and loaded and build.modFlag then
			fail("UNSAVED_CHANGES", "Сначала сохраните текущую сборку в окне PoB")
		end
	end
	local params = request.params or {}
	if type(params) ~= "table" then fail("INVALID_REQUEST", "params должен быть объектом") end
	local requiresBuild = request.method ~= "initialize" and request.method ~= "createBuild" and request.method ~= "getCatalog" and request.method ~= "loadBuild" and request.method ~= "shutdown"
	if requiresBuild and not loaded then fail("INVALID_BUILD", "Сначала откройте сборку") end
	if (requiresBuild or host.live and mutations[request.method]) and params.revision ~= revision then fail("STALE_REVISION", "Ревизия сборки устарела") end
	if host.live and mutations[request.method] and host.blocked and host.blocked() then
		fail("APP_BUSY", "Сначала закройте диалог в окне PoB")
	end
	local previous = loaded and mutations[request.method] and build:SaveDB("rollback") or nil
	local previousMode = loaded and build.spec.allocMode
	local previousCompare = loaded and build.treeTab.isComparing
	local previousCompareId = loaded and build.treeTab.activeCompareSpec
	local previousFile = loaded and build.dbFileName
	local previousName = loaded and build.buildName
	local previousDirty = loaded and build.modFlag
	local ok, result = pcall(method, params)
	if not ok then
		if previous then
			local restored = pcall(loadBuildFromXML, previous, "MCP session")
			if not restored then running = false; fail("CALCULATION_FAILED", "Восстановление не удалось; перезапустите процесс") end
			build.dbFileName, build.buildName, build.modFlag = previousFile, previousName, previousDirty
			build.spec.allocMode = previousMode
			build.spec:BuildAllDependsAndPaths()
			build.treeTab.isComparing = previousCompare
			build.treeTab:SetCompareSpec(previousCompareId)
			build.treeTab.viewer.compareSpec = previousCompare and build.treeTab.compareSpec or nil
			if host.live then lastXML = build:SaveDB("MCP session") end
		end
		if type(result) == "table" then error(result, 0) end
		fail("CALCULATION_FAILED", tostring(result))
	end
	if request.method == "createBuild" then loaded = true end
	if mutations[request.method] then revision = revision + 1 end
	if host.live and loaded then
		build.modFlag = build.modFlag or mutations[request.method] == true
		lastXML = build:SaveDB("MCP session")
	end
	return result
end
local function handle(line)
	local request
	local ok, result = pcall(function()
		if #line > 8 * 1024 * 1024 then fail("INVALID_REQUEST", "Запрос превышает лимит") end
		local position, decodeError
		request, position, decodeError = json.decode(line)
		if decodeError or not position or line:sub(position):match("%S") then fail("INVALID_REQUEST", "Некорректный JSON") end
		return dispatch(request)
	end)
	local response = { protocol = 1, id = type(request) == "table" and request.id or json.null, revision = revision }
	if ok then response.result = result
	else response.error = type(result) == "table" and result or { code = "CALCULATION_FAILED", message = tostring(result), recoverable = true } end
	return json.encode(response)
end
return { handle = handle, is_running = function() return running end }
end
