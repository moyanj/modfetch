--[[
    配置检查器 Lua 插件示例

    演示如何使用配置 API 检查和操作配置。
--]]

plugin = {
    name = "config_inspector",
    version = "1.0.0",
    description = "配置检查器示例插件",
    author = "ModFetch Team"
}

function on_plugin_load(context)
    modfetch.log("info", "Config Inspector 插件已加载")
    return { success = true }
end

function on_config_loaded(context)
    modfetch.log("info", "========== 配置检查器报告 ==========")

    -- 获取完整配置
    local config = modfetch.config.get()
    modfetch.log("info", "完整配置: " .. modfetch.json_encode(config))

    -- 获取 Minecraft 配置
    local mc_config = modfetch.config.get_minecraft()
    modfetch.log("info", "Minecraft 版本: " .. modfetch.json_encode(mc_config.version))
    modfetch.log("info", "模组加载器: " .. mc_config.mod_loader)
    modfetch.log("info", "模组数量: " .. tostring(#mc_config.mods))

    -- 列出所有模组
    modfetch.log("info", "模组列表:")
    for i, mod in ipairs(mc_config.mods) do
        local mod_str = ""
        if mod.id then
            mod_str = mod_str .. "id=" .. mod.id
        end
        if mod.slug then
            if #mod_str > 0 then mod_str = mod_str .. ", " end
            mod_str = mod_str .. "slug=" .. mod.slug
        end
        modfetch.log("info", "  [" .. tostring(i) .. "] " .. mod_str)
    end

    -- 获取输出配置
    local output_config = modfetch.config.get_output()
    if output_config and output_config.download_dir then
        modfetch.log("info", "下载目录: " .. output_config.download_dir)
        modfetch.log("info", "输出格式: " .. modfetch.json_encode(output_config.format))
    else
        modfetch.log("warning", "输出配置未设置")
    end

    -- 获取本插件的配置
    local plugin_config_data = modfetch.config.get_plugin("config_inspector")
    if next(plugin_config_data) then
        modfetch.log("info", "本插件配置: " .. modfetch.json_encode(plugin_config_data))
    else
        modfetch.log("info", "本插件没有特定配置")
    end

    -- 获取所有模组（另一种方式）
    local all_mods = modfetch.config.get_mods()
    modfetch.log("info", "通过 get_mods() 获取的模组数量: " .. tostring(#all_mods))

    modfetch.log("info", "====================================")

    return { success = true }
end

function on_pre_resolve(context)
    modfetch.log("debug", "Config Inspector: 准备解析模组")
    return { success = true }
end

function on_post_resolve(context)
    local mod_entry = context.mod_entry

    if mod_entry then
        modfetch.log("debug", "Config Inspector: 解析完成 - " .. (mod_entry.id or mod_entry.slug or "unknown"))
    end

    return { success = true }
end

function on_pre_download(context)
    modfetch.log("debug", "Config Inspector: 准备下载")
    return { success = true }
end

function on_post_download(context)
    modfetch.log("debug", "Config Inspector: 下载完成")
    return { success = true }
end

function on_post_package(context)
    modfetch.log("info", "Config Inspector: 打包完成")
    return { success = true }
end

function on_plugin_unload(context)
    modfetch.log("info", "Config Inspector 插件已卸载")
    return { success = true }
end
