-- Транспорт отдельного движка: одна строка JSON на сообщение.
local protocolOutput = io.stdout
dofile(POB_MCP_PACKAGE_DIR .. "/lua/headless_bootstrap.lua")
local session = dofile(POB_MCP_PACKAGE_DIR .. "/lua/session.lua")({
	get_build = function() return build end,
	new_build = newBuild,
	load_build = loadBuildFromXML,
	frame = function() return runCallback("OnFrame") end,
}, POB_MCP_PACKAGE_DIR)
while session.is_running() do
	local line = io.stdin:read("*l")
	if not line then break end
	protocolOutput:write(session.handle(line), "\n")
	protocolOutput:flush()
end
