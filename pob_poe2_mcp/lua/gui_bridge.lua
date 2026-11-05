-- Локальный мост выполняет команды в том же Lua-состоянии, что окно PoB.
local json = require("dkjson")
local socket = require("socket")
local MAX_MESSAGE = 8 * 1024 * 1024

return function(launch, directory)
local configFile = assert(io.open(directory .. "/config.json", "rb"))
local config = assert(json.decode(configFile:read("*a")))
configFile:close()
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
local client, partial, output, outputIndex
local function disconnect()
	if client then client:close() end
	client, partial, output, outputIndex = nil, "", nil, 1
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
	if type(request) ~= "table" or request.token ~= config.token then disconnect(); return end
	output, outputIndex = session.handle(line) .. "\n", 1
end
local function send()
	local sent, status, last = client:send(output, outputIndex)
	outputIndex = (sent or last or outputIndex - 1) + 1
	if status == "closed" then disconnect(); return end
	if outputIndex > #output then output = nil end
end
local function poll()
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
