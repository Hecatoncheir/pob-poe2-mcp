-- Запросы выполняет авторизованный PoB. По мосту передаются только данные персонажа.
local json = require("dkjson")
local methods = { listCharacters = true, getCharacter = true }

local function failure(code, message)
	return { code = code, message = message, recoverable = true }
end

local function notAuthorized()
	return failure("POE_AUTH_REQUIRED", "Войдите в аккаунт Path of Exile в оригинальном PoB.")
end

local function unavailable()
	return failure("POE_CHARACTER_UNAVAILABLE", "PoB не смог загрузить данные персонажей. Попробуйте ещё раз.")
end

local function summary(character)
	if type(character) ~= "table" or type(character.name) ~= "string" or character.name == ""
		or type(character.class) ~= "string" or type(character.level) ~= "number" then return nil end
	return { name = character.name, class = character.class, level = character.level, league = character.league }
end

local function list(data)
	if type(data.characters) ~= "table" then return nil end
	local characters = setmetatable({}, { __jsontype = "array" })
	for _, character in ipairs(data.characters) do
		local entry = summary(character)
		if entry and not character.deleted and not character.expired then characters[#characters + 1] = entry end
	end
	return { characters = characters }
end

local function details(data, name)
	local character = data.character
	local entry = summary(character)
	if not entry or entry.name ~= name or type(character.passives) ~= "table" then return nil end
	entry.equipment = character.equipment
	entry.skills = character.skills
	entry.passives = character.passives
	entry.jewels = character.jewels
	return { character = entry }
end

return function()
	local job
	local function complete(active, result, error)
		if job ~= active then return end
		job = nil
		active.reply(result, error)
	end
	local function poll()
		if not job then return end
		if not job.api.authToken then complete(job, nil, notAuthorized())
		elseif os.time() >= job.deadline then complete(job, nil, unavailable()) end
	end
	local function handle(request, reply)
		local method = request.method
		if not methods[method] then return false end
		local params = request.params
		if request.protocol ~= 1 or type(request.id) ~= "string" or type(params) ~= "table" then
			reply(nil, failure("INVALID_REQUEST", "Некорректный запрос списка персонажей."))
			return true
		end
		local name = params.name
		if method == "getCharacter" and (type(name) ~= "string" or name == "" or #name > 256) then
			reply(nil, failure("INVALID_REQUEST", "Укажите имя персонажа."))
			return true
		end
		local importTab = main.mode == "BUILD" and main.modes.BUILD.importTab
		local mode = importTab and importTab.charImportMode
		if job or mode == "IMPORTING" or mode == "DOWNLOADCHARLIST" then
			reply(nil, failure("APP_BUSY", "Дождитесь завершения загрузки в оригинальном PoB."))
			return true
		end
		if not main.api and main.lastToken then
			main.api = new("PoEAPI", main.lastToken, main.lastRefreshToken, main.tokenExpiry)
		end
		local api = main.api
		if not api or not api.authToken or not api.refreshToken then
			reply(nil, notAuthorized())
			return true
		end
		local active = { api = api, reply = reply, deadline = os.time() + 45 }
		job = active
		local function done(body, error)
			if job ~= active then return end
			if not api.authToken or (error and error == api.ERROR_NO_AUTH) then
				complete(active, nil, notAuthorized())
				return
			end
			if error == "Response code: 429" then
				complete(active, nil, failure("POE_RATE_LIMIT", "Слишком много запросов. Повторите попытку позже."))
				return
			end
			-- Некоторые версии PoB не передают признак обновления сеанса в обратный вызов.
			if api.authToken ~= main.lastToken or api.refreshToken ~= main.lastRefreshToken then api:UpdateMain() end
			local data = not error and type(body) == "string" and json.decode(body)
			local result
			if type(data) == "table" then
				if method == "listCharacters" then result = list(data)
				else result = details(data, name) end
			end
			complete(active, result, not result and unavailable() or nil)
		end
		local function download()
			if method == "listCharacters" then api:DownloadCharacterList("poe2", done)
			else api:DownloadCharacter("poe2", urlEncode(name), done) end
		end
		local ok = pcall(download)
		if not ok then complete(active, nil, unavailable()) end
		return true
	end
	return { handle = handle, poll = poll }
end
