-- Предметы разбирает Item, совместимость и описание определяет исходный ItemsTab.
return function(methods, fail, finish)
local function equipmentSlot(name)
	local slot = build.itemsTab.slots[name]
	if not slot or slot.nodeId then fail("INVALID_REQUEST", "Слот экипировки не найден") end
	return slot
end
local function readItem(params)
	if params.raw ~= nil then
		if params.itemId ~= nil or type(params.raw) ~= "string" or #params.raw == 0 or #params.raw > 65536 then
			fail("INVALID_REQUEST", "Нужен текст предмета либо его ID")
		end
		local item = construct("Item", params.raw)
		if not item.base then fail("INVALID_REQUEST", "Lua не распознал базу предмета") end
		return item
	end
	local item = build.itemsTab.items[params.itemId]
	if not item or not item.base then fail("INVALID_REQUEST", "Предмет не найден или его база недоступна") end
	return item
end
local function unsupported(item)
	local result = {}
	for _, list in ipairs({ item.implicitModLines or {}, item.explicitModLines or {}, item.enchantModLines or {}, item.buffModLines or {} }) do
		for _, line in ipairs(list) do
			if line.extra or not line.modList or #line.modList == 0 then result[#result + 1] = { line = line.line, extra = line.extra } end
		end
	end
	return result
end
local function tooltip(item, slot)
	local collector = { lines = {} }
	function collector:AddLine(size, text)
		if type(text) == "string" and text:match("%S") and not text:find("Tip: ", 1, true) then self.lines[#self.lines + 1] = { size = size, text = text } end
	end
	function collector:AddSeparator()
		if #self.lines > 0 and not self.lines[#self.lines].separator then self.lines[#self.lines + 1] = { separator = true } end
	end
	build.itemsTab:AddItemTooltip(collector, item, slot, false)
	if collector.lines[#collector.lines] and collector.lines[#collector.lines].separator then table.remove(collector.lines) end
	return collector.lines
end
function methods.inspectItem(params)
	local item = readItem(params)
	local slots = {}
	for _, slot in ipairs(build.itemsTab.orderedSlots) do
		if not slot.nodeId and build.itemsTab:IsItemValidForSlot(item, slot.slotName) then slots[#slots + 1] = slot.slotName end
	end
	local slot = params.slot and equipmentSlot(params.slot)
	return { source = "original-lua", item = { id = item.id, name = item.name, base = item.baseName,
		rarity = item.rarity, raw = item.raw, unsupported = unsupported(item) }, slots = slots,
		compatible = slot and build.itemsTab:IsItemValidForSlot(item, slot.slotName) == true or false,
		lines = tooltip(item, slot) }
end
function methods.equipItem(params)
	local slot = equipmentSlot(params.slot)
	if params.itemId == 0 and params.raw == nil then
		slot:SetSelItemId(0)
	else
		local item = readItem(params)
		if not build.itemsTab:IsItemValidForSlot(item, slot.slotName) then fail("INVALID_REQUEST", "Предмет несовместим со слотом") end
		if params.raw ~= nil then build.itemsTab:AddItem(item, true) end
		slot:SetSelItemId(item.id)
	end
	build.itemsTab:PopulateSlots()
	build.itemsTab:UpdateSockets()
	return finish()
end
function methods.selectWeaponSet(params)
	if params.index ~= 1 and params.index ~= 2 then fail("INVALID_REQUEST", "Набор оружия должен быть I или II") end
	build.itemsTab.controls["weaponSwap" .. params.index].onClick()
	return finish()
end
end
