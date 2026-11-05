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

    function methods.getTreeGeometry()
        local result = imageTree()
        result.version = build.spec.treeVersion
        result.pointDisplay = build.controls.pointDisplay.str
        return result
    end
end
