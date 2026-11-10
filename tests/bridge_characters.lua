local bridge = dofile(POB_MCP_PACKAGE_DIR .. "/lua/bridge_characters.lua")()
local json = require("dkjson")
local response, errorCode, pending
main = { mode = "LIST" }
function urlEncode(name)
	assert(name == "Тест")
	return "%D0%A2%D0%B5%D1%81%D1%82"
end
local function call(method, name)
	response, errorCode = nil, nil
	assert(bridge.handle({ protocol = 1, id = "test", method = method, params = { name = name } }, function(result, err)
		response, errorCode = result, err and err.code
	end))
end

call("listCharacters")
assert(errorCode == "POE_AUTH_REQUIRED")
main.lastToken, main.lastRefreshToken = "токен", "токен обновления"
main.api = {
	authToken = main.lastToken,
	refreshToken = main.lastRefreshToken,
	ERROR_NO_AUTH = "No auth token",
	DownloadCharacterList = function(self, realm, done)
		assert(realm == "poe2")
		pending = done
	end,
	DownloadCharacter = function(self, realm, name, done)
		assert(realm == "poe2" and name == "%D0%A2%D0%B5%D1%81%D1%82")
		pending = done
	end,
}
local character = { name = "Тест", class = "Witch", level = 90, league = "Standard",
	equipment = { "экипировка" }, skills = { "умение" }, passives = {}, jewels = { "самоцвет" },
	inventory = { "личное содержимое инвентаря" }, authToken = "токен" }

call("listCharacters")
assert(not response and not errorCode)
call("getCharacter", character.name)
assert(errorCode == "APP_BUSY")
pending(json.encode({ characters = { character, { name = "Удалён", class = "Witch", level = 90, deleted = true } } }))
assert(#response.characters == 1 and response.characters[1].name == character.name)
assert(not response.characters[1].equipment and not response.characters[1].authToken)
call("getCharacter", character.name)
pending(json.encode({ character = character }))
assert(response.character.equipment[1] == "экипировка" and response.character.skills[1] == "умение")
assert(response.character.passives and response.character.jewels[1] == "самоцвет")
assert(not response.character.inventory and not response.character.authToken)
call("listCharacters")
pending(0, "Response code: 429")
assert(errorCode == "POE_RATE_LIMIT")
call("listCharacters")
main.api.authToken = nil
bridge.poll()
assert(errorCode == "POE_AUTH_REQUIRED")
pending(json.encode({ characters = {} }))
assert(not response and errorCode == "POE_AUTH_REQUIRED")
io.stdout:write("BRIDGE_CHARACTERS_OK\n")
