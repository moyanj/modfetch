--[[
    统计信息 Lua 插件示例

    演示如何收集和输出下载统计信息。
--]]

plugin = {
    name = "stats",
    version = "1.0.0",
    description = "下载统计插件",
    author = "ModFetch Team"
}

-- 统计数据
local stats = {
    start_time = 0,
    end_time = 0,
    total_mods = 0,
    downloaded = 0,
    failed = 0,
    mods = {}
}

function on_plugin_load(context)
    modfetch.log("info", "Stats 插件已加载")
    stats.start_time = os.time()

    return { success = true }
end

function on_plugin_unload(context)
    stats.end_time = os.time()

    -- 输出统计报告
    local duration = stats.end_time - stats.start_time
    modfetch.log("info", "========== 下载统计 ==========")
    modfetch.log("info", "总耗时: " .. tostring(duration) .. " 秒")
    modfetch.log("info", "总模组数: " .. tostring(stats.total_mods))
    modfetch.log("info", "成功下载: " .. tostring(stats.downloaded))
    modfetch.log("info", "下载失败: " .. tostring(stats.failed))

    if stats.failed > 0 then
        modfetch.log("info", "失败的模组:")
        for _, mod in ipairs(stats.mods) do
            if not mod.success then
                modfetch.log("info", "  - " .. mod.name .. ": " .. (mod.error or "unknown"))
            end
        end
    end

    modfetch.log("info", "==============================")

    return { success = true }
end

function on_pre_resolve(context)
    modfetch.log("info", "Stats: 开始收集统计信息")

    return { success = true }
end

function on_post_resolve(context)
    local config = context.config
    stats.total_mods = config.mods_count or 0
    modfetch.log("info", "Stats: 需要下载 " .. tostring(stats.total_mods) .. " 个模组")

    return { success = true }
end

function on_post_download(context)
    stats.downloaded = stats.downloaded + 1

    local mod_entry = context.mod_entry
    if mod_entry then
        table.insert(stats.mods, {
            name = mod_entry.name or mod_entry.id or "unknown",
            id = mod_entry.id,
            version = mod_entry.version,
            success = true
        })

        modfetch.log("info", "Stats: 已下载 " .. tostring(stats.downloaded) .. "/" .. tostring(stats.total_mods))
    end

    return { success = true }
end

function on_download_failed(context)
    stats.failed = stats.failed + 1

    local mod_entry = context.mod_entry
    if mod_entry then
        table.insert(stats.mods, {
            name = mod_entry.name or mod_entry.id or "unknown",
            id = mod_entry.id,
            version = mod_entry.version,
            success = false,
            error = "下载失败"
        })
    end

    return { success = true }
end

function on_post_package(context)
    modfetch.log("info", "Stats: 打包完成")

    return { success = true }
end
