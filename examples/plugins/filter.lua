--[[
    模组过滤 Lua 插件示例

    演示如何使用 Lua 插件过滤模组列表。
--]]

plugin = {
    name = "filter",
    version = "1.0.0",
    description = "模组过滤插件示例",
    author = "ModFetch Team"
}

-- 配置示例：
-- plugin_config = {
--     blocked_mods = {"mod1", "mod2"},
--     min_version = "1.0.0"
-- }

function on_config_loaded(context)
    modfetch.log("info", "Filter 插件已加载")

    -- 读取配置
    local blocked = plugin_config.blocked_mods or {}
    modfetch.log("info", "已配置的屏蔽模组数量: " .. tostring(#blocked))

    return { success = true }
end

function on_pre_resolve(context)
    modfetch.log("info", "Filter: 准备解析模组...")

    return { success = true }
end

function on_post_resolve(context)
    modfetch.log("info", "Filter: 模组解析完成")

    -- 这里可以访问解析后的模组信息
    local mod_entry = context.mod_entry
    if mod_entry then
        modfetch.log("debug", "处理模组: " .. (mod_entry.name or "unknown"))
    end

    return { success = true }
end

function on_pre_download(context)
    -- 检查是否应该下载这个模组
    local mod_entry = context.mod_entry
    if mod_entry then
        local mod_id = mod_entry.id or ""
        local blocked_mods = plugin_config.blocked_mods or {}

        -- 检查是否在屏蔽列表中
        for _, blocked in ipairs(blocked_mods) do
            if mod_id == blocked then
                modfetch.log("warning", "模组 " .. mod_id .. " 在屏蔽列表中，跳过下载")
                return {
                    success = false,
                    should_stop = true,
                    error = "模组在屏蔽列表中"
                }
            end
        end
    end

    return { success = true }
end
