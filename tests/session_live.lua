-- Проверка общего API в режиме текущей сборки без графического окна.
dofile(POB_MCP_PACKAGE_DIR .. "/lua/headless_bootstrap.lua")
local json = require("dkjson")
local opened = false
local session = dofile(POB_MCP_PACKAGE_DIR .. "/lua/session.lua")({
	live = true,
	get_build = function() if opened then return build end end,
	get_build_directory = function() return "C:/PoB/Custom Builds/" end,
	new_build = newBuild,
	load_build = loadBuildFromXML,
	frame = function() return runCallback("OnFrame") end,
}, POB_MCP_PACKAGE_DIR)
local revision = 0
local function call(method, params)
	params = params or {}
	if params.revision == nil then params.revision = revision end
	local response = assert(json.decode(session.handle(json.encode({ protocol = 1, id = "test", method = method, params = params }))))
	revision = response.revision
	return response
end
local system = jit.os == "OSX" and "macos" or jit.os:lower()
assert(call("initialize").result.platform == system .. "-app")
assert(call("getBuildDirectory").result.directory == "C:/PoB/Custom Builds/")
opened = true
build.modFlag = false
assert(call("createBuild", { name = "Live API test", level = 42 }).result.buildInfo.level == 42)
local original = call("getBuildReport").result.stats.Life
assert(call("setCustomMods", { text = "100% increased maximum Life" }).result)
assert(call("getBuildReport").result.stats.Life > original)
local oldRevision = revision
build.controls.characterLevel:SetText("43", true)
runCallback("OnFrame")
assert(call("getBuildReport", { revision = oldRevision }).error.code == "STALE_REVISION")
assert(call("getBuildReport").result.snapshot.buildInfo.level == 43)
assert(call("createBuild", { level = 1 }).error.code == "UNSAVED_CHANGES")
build.dbFileName, build.buildName, build.modFlag = "original.xml", "Original name", false
local failed = call("addItem", { raw = "Rarity: Normal\nWithered Wand\n", slot = "Boots" })
assert(failed.error.code == "INVALID_REQUEST")
assert(build.dbFileName == "original.xml" and build.buildName == "Original name" and not build.modFlag)
io.stdout:write("LIVE_SESSION_OK\n")
