-- Локальная подготовка ссылки; категории, базы, характеристики и валюты читает PoB.
return function(methods, fail)
local json = require("dkjson")
local helpers, stats, statsById, currencies
local function slotFor(name)
	local slot = build.itemsTab.slots[name]
	if not slot or slot.nodeId then fail("INVALID_REQUEST", "Ячейка экипировки не найдена") end
	return slot
end
local function tradeData()
	if stats then return end
	helpers = LoadModule("Classes/TradeHelpers")
	stats, statsById = {}, {}
	for _, group in ipairs(helpers.getTradeStats()) do
		for _, entry in ipairs(group.entries) do
			if not statsById[entry.id] then
				local queryId, fixedOption = entry.id:match("^(.*)|(.*)$")
				local row = { id = entry.id, label = entry.text, type = group.id, numeric = entry.text:find("#", 1, true) ~= nil,
					options = entry.option and entry.option.options, queryId = queryId or entry.id, fixedOption = fixedOption }
				stats[#stats + 1], statsById[entry.id] = row, row
			end
		end
	end
	table.sort(stats, function(a, b) return a.label == b.label and a.id < b.id or a.label < b.label end)
end
local function currencyData()
	if currencies then return currencies end
	LoadModule("Classes/TradeQueryGenerator")
	-- Список локален в исходном классе: читаем его замыкание, не вызывая сетевой InitMods.
	for index = 1, 100 do
		local name, value = debug.getupvalue(common.classes.TradeQueryGenerator.StartQuery, index)
		if not name then break end
		if name == "currencyTable" then
			currencies = {}
			for _, entry in ipairs(value) do
				if entry.id then currencies[#currencies + 1] = { id = entry.id, label = entry.name } end
			end
			return currencies
		end
	end
	fail("UNSUPPORTED_OPERATION", "В этой версии PoB не найден список валют торговли")
end
local function itemBase(name)
	local base = build.data.itemBases[name]
	return base and { base = base, baseName = name, type = base.type, rarity = "NORMAL" }
end
local function searchItem(slot, baseName)
	if not baseName then return build.itemsTab.items[slot.selItemId] end
	local item = itemBase(baseName)
	if not item or item.base.hidden or not build.itemsTab:IsItemValidForSlot(item, slot.slotName) then fail("INVALID_REQUEST", "База предмета не подходит к ячейке") end
	return item
end
function methods.getTradeCatalog(params)
	local slot = slotFor(params.slot)
	tradeData()
	local bases = {}
	for name, base in pairs(build.data.itemBases) do
		if not base.hidden and build.itemsTab:IsItemValidForSlot(itemBase(name), slot.slotName) then bases[#bases + 1] = name end
	end
	table.sort(bases)
	local category = helpers.getTradeCategory(slot.slotName, searchItem(slot))
	if not category then fail("UNSUPPORTED_OPERATION", "В PoB нет торговой категории для этой ячейки") end
	return { source = "original-lua", stats = stats, bases = bases, currencies = currencyData(), category = category }
end
local function filterValue(input, entry)
	if entry.options then
		for _, option in ipairs(entry.options) do
			if tostring(option.id) == input.option then return { option = option.id } end
		end
		fail("INVALID_REQUEST", "Выберите вариант характеристики из каталога PoB")
	end
	if input.option ~= nil then fail("INVALID_REQUEST", "У характеристики нет вариантов") end
	if input.min and input.max and input.min > input.max then fail("INVALID_REQUEST", "Минимум не может быть больше максимума") end
	local value = { min = input.min, max = input.max }
	if entry.fixedOption then value.option = tonumber(entry.fixedOption) or entry.fixedOption end
	return setmetatable(value, { __jsontype = "object" })
end
function methods.buildTradeSearch(params)
	local slot = slotFor(params.slot)
	if type(params.league) ~= "string" or not params.league:match("%S") or params.league:find("%c") then fail("INVALID_REQUEST", "Укажите название лиги") end
	tradeData()
	local category = helpers.getTradeCategory(slot.slotName, searchItem(slot, params.base))
	if not category then fail("UNSUPPORTED_OPERATION", "В PoB нет торговой категории для этой ячейки") end
	local filters, seen = {}, {}
	for _, input in ipairs(params.filters or {}) do
		local entry = statsById[input.id]
		if not entry or seen[input.id] then fail("INVALID_REQUEST", "Неизвестная или повторная характеристика") end
		seen[input.id] = true
		filters[#filters + 1] = { id = entry.queryId, value = filterValue(input, entry) }
	end
	local query = { query = { status = { option = params.online == false and "any" or "online" },
		filters = { type_filters = { filters = { category = { option = category } } } },
		stats = { { type = "and", filters = filters } }, type = params.base }, sort = { price = "asc" } }
	if params.maxPrice then
		local valid = false
		for _, currency in ipairs(currencyData()) do if currency.id == params.currency then valid = true end end
		if not valid then fail("INVALID_REQUEST", "Выберите валюту из каталога PoB") end
		query.query.filters.trade_filters = { filters = { price = { option = params.currency, max = params.maxPrice } } }
	end
	LoadModule("Classes/TradeQueryRequests")
	local url = common.classes.TradeQueryRequests.buildUrl({}, "https://www.pathofexile.com/trade2/search", "poe2", params.league)
	url = url .. "?q=" .. urlEncode(json.encode(query))
	return { source = "original-lua", url = url, query = query }
end
end
