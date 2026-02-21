--[[
    Modrinth API Lua 插件示例

    演示如何使用 Modrinth API 查询模组信息。
--]]

plugin = {
    name = "modrinth_api",
    version = "1.0.0",
    description = "Modrinth API 查询示例",
    author = "ModFetch Team"
}

function on_plugin_load(context)
    modfetch.log("info", "Modrinth API 插件已加载")
    return { success = true }
end

function on_config_loaded(context)
    modfetch.log("info", "Modrinth API: 配置已加载")

    -- 获取配置信息
    local config = modfetch.config.get()
    modfetch.log("debug", "Minecraft 版本: " .. modfetch.json_encode(config.minecraft.version))
    modfetch.log("debug", "模组加载器: " .. config.minecraft.mod_loader)

    return { success = true }
end

function on_pre_resolve(context)
    modfetch.log("info", "Modrinth API: 准备解析模组")

    -- 获取所有模组列表
    local mods = modfetch.config.get_mods()
    modfetch.log("info", "需要解析的模组数量: " .. tostring(#mods))

    -- 显示前5个模组
    for i = 1, math.min(5, #mods) do
        local mod = mods[i]
        modfetch.log("debug", "  [" .. tostring(i) .. "] " .. (mod.id or mod.slug or "unknown"))
    end

    return { success = true }
end

function on_post_resolve(context)
    local mod_entry = context.mod_entry

    if mod_entry then
        local mod_id = mod_entry.id or mod_entry.slug
        modfetch.log("info", "Modrinth API: 解析模组 " .. mod_id)

        -- 注意：这里演示 API 调用，实际使用需要在异步环境中
        -- 由于 Lua 插件中的异步调用需要特殊处理，这里仅作示例

        -- 示例：查询项目信息（需要在支持异步的 Hook 中使用）
        -- local result = modfetch.modrinth.get_project(mod_id)
        -- if result.success then
        --     modfetch.log("info", "项目标题: " .. result.title)
        --     modfetch.log("info", "项目描述: " .. result.description)
        -- end
    end

    return { success = true }
end

function on_pre_download(context)
    local mod_entry = context.mod_entry

    if mod_entry then
        local mod_id = mod_entry.id or mod_entry.slug
        modfetch.log("info", "Modrinth API: 准备下载 " .. mod_id)

        -- 获取 Minecraft 版本和加载器信息
        local mc_config = modfetch.config.get_minecraft()
        local mc_version = mc_config.version[1] or "1.21.1"
        local mod_loader = mc_config.mod_loader or "fabric"

        modfetch.log("debug", "目标版本: " .. mc_version)
        modfetch.log("debug", "模组加载器: " .. mod_loader)

        -- 示例：获取版本信息（需要在支持异步的 Hook 中使用）
        -- local result = modfetch.modrinth.get_version(mod_id, mc_version, mod_loader)
        -- if result.success then
        --     modfetch.log("info", "版本: " .. result.version.version)
        --     modfetch.log("info", "文件名: " .. (result.file and result.file.filename or "N/A"))
        -- end
    end

    return { success = true }
end

function on_post_package(context)
    modfetch.log("info", "Modrinth API: 打包完成")

    -- 获取输出配置
    local output_config = modfetch.config.get_output()
    modfetch.log("info", "输出目录: " .. output_config.download_dir)
    modfetch.log("info", "输出格式: " .. modfetch.json_encode(output_config.format))

    return { success = true }
end

function on_plugin_unload(context)
    modfetch.log("info", "Modrinth API 插件已卸载")
    return { success = true }
end
