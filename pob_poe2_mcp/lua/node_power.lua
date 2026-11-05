-- Поэтапный доступ к штатному отчёту PoB без переноса игровых формул.
return function(methods, fail)
    local job, sequence = nil, 0
    local function catalog()
        local entries = {}
        for _, stat in ipairs(build.treeTab.powerStatList) do
            if (stat.stat or stat.combinedOffDef) and not stat.ignoreForNodes then
                entries[#entries + 1] = {id = stat.stat or "OffenceDefence", label = stat.label}
            end
        end
        return {entries = entries}
    end
    local function restore()
        if not job then return end
        local calcs = job.build.calcsTab
        calcs.powerStat, calcs.nodePowerMaxDepth = job.previous.stat, job.previous.depth
        calcs.powerBuilder, calcs.powerBuildFlag = nil, true
        job.build.powerBuilderProgressCallback = job.previous.progress
    end
    local function start(params)
        local selection
        for _, stat in ipairs(build.treeTab.powerStatList) do
            local key = stat.stat or (stat.combinedOffDef and "OffenceDefence")
            if key == params.stat and not stat.ignoreForNodes then selection = stat; break end
        end
        if not selection then fail("INVALID_REQUEST", "Выберите характеристику из каталога") end
        local depth = params.maxDistance
        if depth ~= nil and (type(depth) ~= "number" or depth % 1 ~= 0 or depth < 1 or depth > 200) then
            fail("INVALID_REQUEST", "Расстояние должно быть целым от 1 до 200")
        end
        restore()
        build.spec:BuildAllDependsAndPaths()
        local calcs = build.calcsTab
        sequence = sequence + 1
        job = {id = sequence, build = build, revision = params.revision, stat = selection, depth = depth,
            progress = 0, previous = {stat = calcs.powerStat, depth = calcs.nodePowerMaxDepth,
                progress = build.powerBuilderProgressCallback}}
        calcs.powerStat, calcs.nodePowerMaxDepth = selection, depth
        calcs.powerBuilder, calcs.powerMax, calcs.powerBuildFlag = nil, nil, false
        build.powerBuilderProgressCallback = function(percent) job.progress = percent end
        job.thread = coroutine.create(calcs.PowerBuilder)
        return {job = job.id, complete = false, progress = 0}
    end
    local function report(params)
        local entries = {}
        for _, row in ipairs(build.treeTab:BuildPowerReportList(job.stat)) do
            local distance = row.pathDist
            local inRange = not job.depth or type(distance) == "number" and distance <= job.depth
            local allocated = row.allocated == true
            local filter = params.allocation or "unallocated"
            local visible = filter == "all" or (filter == "allocated") == allocated
            if visible and inRange and row.power ~= 0 and build.spec.nodes[row.id] then
                entries[#entries + 1] = row
            end
        end
        local result = {job = job.id, complete = true, progress = 100, stat = job.stat.stat or "OffenceDefence",
            label = job.stat.label, maxDistance = job.depth, entries = entries}
        if params.includeScene then
            local capture = dofile(POB_MCP_PACKAGE_DIR .. "/lua/tree_scene.lua")
            setfenv(capture, getfenv(1))
            result.scene = capture(build, {treeScope = "full", width = 1856, height = 2034, power = true})
        end
        return result
    end
    local function poll(params)
        if not job or params.job ~= job.id then fail("INVALID_REQUEST", "Расчёт не найден или заменён") end
        if job.build ~= build or job.revision ~= params.revision then
            restore(); job = nil
            fail("STALE_REVISION", "Сборка изменилась; запустите расчёт заново")
        end
        if coroutine.status(job.thread) ~= "dead" then
            -- В headless GetTime — заглушка. Штатный PowerBuilder уступает
            -- управление каждые 100 мс только при настоящем ходе часов.
            local originalTime = _G.GetTime
            _G.GetTime = function() return os.clock() * 1000 end
            local ok, err = coroutine.resume(job.thread, build.calcsTab)
            _G.GetTime = originalTime
            if not ok then restore(); job = nil; fail("CALCULATION_FAILED", tostring(err)) end
        end
        if coroutine.status(job.thread) == "dead" then return report(params) end
        return {job = job.id, complete = false, progress = job.progress}
    end
    function methods.getNodePower(params)
        if params.action == "catalog" then return catalog() end
        if params.action == "start" then return start(params) end
        if params.action == "poll" then return poll(params) end
        if params.action == "cancel" then
            if job and params.job == job.id then restore(); job = nil end
            return {cancelled = true}
        end
        fail("INVALID_REQUEST", "Неизвестное действие отчёта")
    end
end
