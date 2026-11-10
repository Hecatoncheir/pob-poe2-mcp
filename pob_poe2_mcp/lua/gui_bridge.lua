-- Локальный мост выполняет команды в том же Lua-состоянии, что окно PoB.
local json = require("dkjson")
local socket = require("socket")
local MAX_MESSAGE = 8 * 1024 * 1024

return function(launch, directory)
local configFile = assert(io.open(directory .. "/config.json", "rb"))
local config = assert(json.decode(configFile:read("*a")))
configFile:close()
local wine = config.hostPlatform == "linux" and jit.os == "Windows"
local server = assert(socket.bind("127.0.0.1", 0))
server:settimeout(0)
local _, port = server:getsockname()
local endpointPath = directory .. "/endpoint.json"
local endpoint = assert(io.open(endpointPath, "wb"))
endpoint:write(json.encode({ port = port, token = config.token, installDir = config.installDir }))
endpoint:close()
local originalFrame = launch.OnFrame
local function getBuild()
	local main = launch.main
	if main and main.mode == "BUILD" and main.modes.BUILD and main.modes.BUILD.spec then return main.modes.BUILD end
end
local host = {
	live = true,
	app_platform = config.hostPlatform,
	character_download = true,
	get_build_directory = function()
		local directory = launch.main.buildPath
		if not wine then return directory end
		local prefix = os.getenv("WINEPREFIX")
		local steamData = os.getenv("STEAM_COMPAT_DATA_PATH")
		if not prefix and steamData then prefix = steamData .. "/pfx" end
		return directory, { prefix = prefix, workingDirectory = GetWorkDir() }
	end,
	get_build = getBuild,
	blocked = function() return launch.promptMsg or #launch.main.popups > 0 end,
	frame = function() return originalFrame(launch) end,
	new_build = function()
		if GlobalCache and GlobalCache.cachedData then wipeGlobalCache() end
		launch.main:SetMode("BUILD", false, "MCP build")
		originalFrame(launch)
	end,
	load_build = function(xml, name)
		launch.main:SetMode("BUILD", false, name or "MCP build", xml)
		originalFrame(launch)
	end,
}
local session = dofile(directory .. "/lua/session.lua")(host, directory)
local characters = dofile(directory .. "/lua/bridge_characters.lua")()
local client, partial, output, outputIndex, waiting
local function disconnect()
	if client then client:close() end
	client, partial, output, outputIndex, waiting = nil, "", nil, 1, false
end
local function accept()
	local nextClient = server:accept()
	if not nextClient then return end
	if client then nextClient:close(); return end
	client, partial, outputIndex = nextClient, "", 1
	client:settimeout(0)
end
local function receive()
	local line, status, fragment = client:receive("*l", partial)
	partial = fragment or ""
	if #partial > MAX_MESSAGE or (line and #line > MAX_MESSAGE) then disconnect(); return end
	if not line then
		if status == "closed" then disconnect() end
		return
	end
	partial = ""
	local request = json.decode(line)
	if waiting or type(request) ~= "table" or request.token ~= config.token then disconnect(); return end
	local requester = client
	waiting = true
	if characters.handle(request, function(result, error)
		if client ~= requester then return end
		waiting = false
		local params = request.params
		local revision = type(params) == "table" and tonumber(params.revision) or 0
		local response = { protocol = 1, id = request.id, revision = revision or 0, result = result, error = error }
		output, outputIndex = json.encode(response) .. "\n", 1
	end) then return end
	waiting = false
	output, outputIndex = session.handle(line) .. "\n", 1
end
local function send()
	local sent, status, last = client:send(output, outputIndex)
	outputIndex = (sent or last or outputIndex - 1) + 1
	if status == "closed" then disconnect(); return end
	if outputIndex > #output then output = nil end
end
local function poll()
	characters.poll()
	if client and not output then receive() end
	if client and output then send() end
	accept()
end
function launch:OnFrame(...)
	local result = originalFrame(self, ...)
	local ok, err = pcall(poll)
	if not ok then disconnect(); ConPrintf("MCP: %s", tostring(err)) end
	return result
end
local originalExit = launch.OnExit
function launch:OnExit(...)
	disconnect()
	server:close()
	os.remove(endpointPath)
	return originalExit(self, ...)
end
ConPrintf("MCP: local bridge ready on 127.0.0.1:%d", port)
end
