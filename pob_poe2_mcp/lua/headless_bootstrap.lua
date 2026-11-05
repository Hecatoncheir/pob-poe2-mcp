-- Последовательный процесс исходного Lua-движка для MCP.
local json = require("dkjson")
function print(...)
	local values = {}
	for index = 1, select("#", ...) do
		values[index] = tostring(select(index, ...))
	end
	io.stderr:write(table.concat(values, "\t"), "\n")
	io.stderr:flush()
end
-- Оригинальная геометрия соединений требует настоящих размеров изображений.
local manifestFile = assert(io.open(POB_MCP_PACKAGE_DIR .. "/data/tree-image-sizes.json", "rb"))
local artManifest = assert(json.decode(manifestFile:read("*a")))
manifestFile:close()
local sourceFile = assert(io.open("TreeData/0_5/tree.json", "rb"))
local sourceTree = assert(json.decode(sourceFile:read("*a")))
sourceFile:close()
local pngSizes = {}
for name, paths in pairs(sourceTree.assets) do
	if artManifest[name] then pngSizes[paths[1]] = artManifest[name] end
end
local originalDofile = dofile
function dofile(path)
	local source = path
	if path == "_SimpleGraphic.def.lua" or path == "HeadlessWrapper.lua" then
		source = POB_MCP_PACKAGE_DIR .. "/lua/" .. path
	end
	local result = originalDofile(source)
	if path == "_SimpleGraphic.def.lua" then
		local originalNewImageHandle = NewImageHandle
		function NewImageHandle()
			local handle = originalNewImageHandle()
			local originalLoad = handle.Load
			function handle:Load(filename, ...)
				self.sourcePath = filename
				self.sourceFlags = {...}
				self.filename = filename:match("[^/]+$")
				originalLoad(self, filename, ...)
			end
			function handle:ImageSize()
				local info = pngSizes[self.filename]
				if info then return info.width, info.height end
				local width, height = self.filename:match("_(%d+)_(%d+)_[^_]+%.dds%.zst$")
				return tonumber(width) or 1, tonumber(height) or 1
			end
			return handle
		end
	end
	return result
end
dofile("HeadlessWrapper.lua")
assert(build, "Движок не инициализирован")
