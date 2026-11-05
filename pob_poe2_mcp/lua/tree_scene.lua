-- Запись оригинальной отрисовки дерева в отдельном Lua-состоянии MCP.
return function(build, params)
    local width, height = (params.width or 1600) - 56, (params.height or 1100) - 234
    local tree, spec = build.spec.tree, build.spec
    local points, query = {}, (params.query or ""):lower()
    for _, node in pairs(spec.nodes) do
        local selected = params.treeScope == "full" or node.alloc
        if query ~= "" then selected = (tostring(node.id) .. " " .. (node.dn or "")):lower():find(query, 1, true) end
        if selected and node.type ~= "OnlyImage" then points[#points + 1] = node end
    end
    assert(#points > 0, "Нет узлов для указанной области дерева")
    local minX, maxX, minY, maxY = math.huge, -math.huge, math.huge, -math.huge
    for _, node in ipairs(points) do
        minX, maxX = math.min(minX, node.x), math.max(maxX, node.x)
        minY, maxY = math.min(minY, node.y), math.max(maxY, node.y)
    end
    local scale = math.min((width - 100) / math.max(600, maxX - minX), (height - 100) / math.max(600, maxY - minY)) * (params.zoom or 1)
    local viewer = construct("PassiveTreeView")
    viewer.zoom = scale * tree.size / math.min(width, height)
    viewer.zoomX, viewer.zoomY = -(minX + maxX) / 2 * scale, -(minY + maxY) / 2 * scale
    viewer.zoomLevel = math.log(viewer.zoom) / math.log(1.2)
    local commands, saved, color = {}, {}, {1, 1, 1, 1}
    local layer, subLayer, blend = 0, 0, "ALPHA"
    local function replace(name, value) saved[name] = _G[name]; _G[name] = value end
    local function append(handle, positions, uv, index, mask)
        local left, top, right, bottom = math.huge, math.huge, -math.huge, -math.huge
        for i = 1, 8, 2 do
            left, right = math.min(left, positions[i]), math.max(right, positions[i])
            top, bottom = math.min(top, positions[i + 1]), math.max(bottom, positions[i + 1])
        end
        if right < 0 or bottom < 0 or left > width or top > height then return end
        local clamp = false
        for _, flag in ipairs(handle and handle.sourceFlags or {}) do if flag == "CLAMP" then clamp = true end end
        commands[#commands + 1] = { file = handle and assert(handle.sourcePath, "Путь текстуры не записан") or "", clamp = clamp,
            positions = positions, uv = uv, index = index or 1, mask = mask, color = {unpack(color)},
            layer = layer, subLayer = subLayer, order = #commands + 1, blend = blend }
    end
    local function textureArgs(extra, coordinateCount, defaults)
        if #extra < coordinateCount then return defaults, extra[1], extra[2] end
        local coordinates = {}
        for i = 1, coordinateCount do coordinates[i] = extra[i] end
        return coordinates, extra[coordinateCount + 1], extra[coordinateCount + 2]
    end
    replace("SetDrawColor", function(r, g, b, a)
        if type(r) == "string" then
            local hex = r:match("%x%x%x%x%x%x") or "FFFFFF"
            r, g, b = tonumber(hex:sub(1, 2), 16) / 255, tonumber(hex:sub(3, 4), 16) / 255, tonumber(hex:sub(5, 6), 16) / 255
        end
        color = {r or 1, g or 1, b or 1, a or 1}
    end)
    replace("GetDrawColor", function() return unpack(color) end)
    replace("SetDrawLayer", function(l, s) layer, subLayer = l or layer, s or 0 end)
    replace("GetDrawLayer", function() return layer, subLayer end)
    replace("SetBlendMode", function(mode) blend = mode end)
    replace("GetCursorPos", function() return -10000, -10000 end)
    replace("IsKeyDown", function() return false end)
    replace("GetTime", function() return 0 end)
    replace("DrawString", function() end)
    replace("DrawImage", function(handle, x, y, w, h, ...)
        local uv, index, mask = textureArgs({...}, 4, {0, 0, 1, 1})
        append(handle, {x, y, x + w, y, x + w, y + h, x, y + h},
            {uv[1], uv[2], uv[3], uv[2], uv[3], uv[4], uv[1], uv[4]}, index, mask)
    end)
    replace("DrawImageQuad", function(handle, x1, y1, x2, y2, x3, y3, x4, y4, ...)
        local uv, index, mask = textureArgs({...}, 8, {0, 0, 1, 0, 1, 1, 0, 1})
        append(handle, {x1, y1, x2, y2, x3, y3, x4, y4}, uv, index, mask)
    end)
    local originalConnectors = tree.connectors
    tree.connectors = {}
    for _, connector in pairs(originalConnectors) do
        local a, b = spec.nodes[connector.nodeId1], spec.nodes[connector.nodeId2]
        local hidden = a.type == "ClassStart" and b.type == "AscendClassStart" or a.type == "AscendClassStart" and b.type == "ClassStart"
        if not hidden then tree.connectors[#tree.connectors + 1] = connector end
    end
    local ok, err = pcall(viewer.Draw, viewer, build, {x = 0, y = 0, width = width, height = height}, {})
    tree.connectors = originalConnectors
    for name, value in pairs(saved) do _G[name] = value end
    assert(ok, err)
    table.sort(commands, function(a, b)
        if a.layer ~= b.layer then return a.layer < b.layer end
        if a.subLayer ~= b.subLayer then return a.subLayer < b.subLayer end
        return a.order < b.order
    end)
    return {width = width, height = height, scale = scale, offsetX = viewer.zoomX + width / 2,
        offsetY = viewer.zoomY + height / 2, commands = commands}
end
