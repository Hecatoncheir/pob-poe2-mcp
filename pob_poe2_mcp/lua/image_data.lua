-- Данные одного кадра для изображений; формулы и состояния остаются в PoB.
return function(methods)
    local function imageTree()
        local nodes, edges = {}, {}
        for id, node in pairs(build.spec.nodes) do
            if type(node.x) == "number" and type(node.y) == "number" and node.type ~= "OnlyImage" then
                nodes[#nodes + 1] = { id = id, x = node.x, y = node.y, name = node.dn or node.name or "",
                    type = node.type, allocated = node.alloc == true, allocMode = node.allocMode or 0,
                    icon = node.icon, drawSize = node.targetSize and node.targetSize.width or 0 }
                for _, other in ipairs(node.linked or {}) do
                    if id < other.id then edges[#edges + 1] = { id, other.id } end
                end
            end
        end
        table.sort(nodes, function(a, b) return a.id < b.id end)
        table.sort(edges, function(a, b)
            if a[1] == b[1] then return a[2] < b[2] end
            return a[1] < b[1]
        end)
        return { nodes = nodes, edges = edges }
    end

    function methods.getBuildImageData(params)
        local result = { report = methods.getBuildReport() }
        if params.view == "tree" then
            result.tree = imageTree()
            local capture = dofile(POB_MCP_PACKAGE_DIR .. "/lua/tree_scene.lua")
            setfenv(capture, getfenv(1))
            result.scene = capture(build, params)
        end
        if params.view == "node" then
            result.tooltip = methods.getNodeTooltip({ id = params.id, compare = false })
        end
        return result
    end

    function methods.getTreeGeometry(params)
        local result = imageTree()
        result.version = build.spec.treeVersion
        result.pointDisplay = build.controls.pointDisplay.str
        if params and params.includeScene then
            local capture = dofile(POB_MCP_PACKAGE_DIR .. "/lua/tree_scene.lua")
            setfenv(capture, getfenv(1))
            result.scene = capture(build, {treeScope = "full", width = 1856, height = 2034})
        end
        return result
    end

    function methods.getTreeIconAssets(params)
        local result = {}
        local known = {}
        for _, node in pairs(build.spec.nodes) do
            if node.icon then known[node.icon] = true end
        end
        for _, key in ipairs(params.icons or {}) do
            local asset = known[key] and build.spec.tree:GetAssetByName(key)
            if asset and asset.handle and asset.handle.sourcePath then
                local uv = asset[2] and {asset[1], asset[2], asset[3], asset[4]} or {0, 0, 1, 1}
                result[#result + 1] = {key = key, file = asset.handle.sourcePath,
                    index = asset[2] and (asset[5] or 1) or (asset[1] or 1), uv = uv}
            else
                result[#result + 1] = {key = key, error = "Иконка отсутствует в исходном дереве PoB"}
            end
        end
        return {icons = result}
    end
end
