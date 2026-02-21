--[[
    加载器版本查询 Lua 插件示例

    演示如何查询 Fabric/Forge/Quilt 加载器版本。
--]]

plugin = {
    name = "loader_version",
    version = "1.0.0",
    description = "加载器版本查询示例",
    author = "ModFetch Team"
}

function on_plugin_load(context)
    modfetch.log("info", "Loader Version 插件已加载")
    return { success = true }
end

function on_config_loaded(context)
    modfetch.log("info", "Loader Version: 配置已加载")

    -- 获取 Minecraft 配置
    local mc_config = modfetch.config.get_minecraft()
    local mc_versions = mc_config.version
    local mod_loader = mc_config.mod_loader

    modfetch.log("info", "Minecraft 版本: " .. modfetch.json_encode(mc_versions))
    modfetch.log("info", "模组加载器: " .. mod_loader)

    -- 注意：实际的版本查询是异步的，需要在支持异步的环境中使用
    -- 这里仅作示例展示如何调用

    for _, mc_version in ipairs(mc_versions) do
        modfetch.log("info", "查询 " .. mc_version .. " 的 " .. mod_loader .. " 版本...")

        -- 示例：获取加载器版本（需要在支持异步的 Hook 中使用）
        -- local result = modfetch.modrinth.get_loader_version(mc_version, mod_loader)
        -- if result.success then
        --     modfetch.log("info", mc_version .. " 的 " .. mod_loader .. " 版本: " .. result.version)
        -- else
        --     modfetch.log("warning", "未找到 " .. mc_version .. " 的 " .. mod_loader .. " 版本")
        -- end
    end

    return { success = true }
end

function on_pre_resolve(context)
    modfetch.log("info", "Loader Version: 准备解析模组")
    return { success = true }
end

function on_post_package(context)
    modfetch.log("info", "Loader Version: 打包完成")
    return { success = true }
end

function on_plugin_unload(context)
    modfetch.log("info", "Loader Version 插件已卸载")
    return { success = true }
end
