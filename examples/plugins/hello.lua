--[[
    Hello World Lua 插件示例

    这是一个简单的 Lua 插件示例，展示了基本的插件结构和 Hook 使用。
--]]

-- 插件元数据
plugin = {
    name = "hello",
    version = "1.0.0",
    description = "一个简单的 Hello World 插件",
    author = "ModFetch Team"
}

-- 配置（由 Python 端传递）
-- plugin_config = {}

-- 插件加载时调用
function on_plugin_load(context)
    modfetch.log("info", "Hello 插件已加载！")
    modfetch.log("info", "插件版本: " .. plugin.version)

    return {
        success = true,
        data = "Hello from Lua!"
    }
end

-- 插件卸载时调用
function on_plugin_unload(context)
    modfetch.log("info", "Hello 插件已卸载")

    return {
        success = true
    }
end

-- 配置加载完成后调用
function on_config_loaded(context)
    local config = context.config
    modfetch.log("info", "配置已加载")
    modfetch.log("debug", "Minecraft 版本: " .. (config.minecraft_version or "unknown"))
    modfetch.log("debug", "模组加载器: " .. (config.mod_loader or "unknown"))
    modfetch.log("debug", "模组数量: " .. tostring(config.mods_count or 0))

    return {
        success = true
    }
end

-- 开始解析模组前调用
function on_pre_resolve(context)
    modfetch.log("info", "开始解析模组...")

    return {
        success = true
    }
end

-- 解析模组完成后调用
function on_post_resolve(context)
    modfetch.log("info", "模组解析完成")

    return {
        success = true
    }
end

-- 开始下载前调用
function on_pre_download(context)
    modfetch.log("info", "开始下载模组...")

    return {
        success = true
    }
end

-- 下载进度更新时调用
function on_download_progress(context)
    local download_info = context.download_info
    if download_info then
        local progress = download_info.progress or 0
        local total = download_info.total or 0
        if total > 0 then
            local percent = (progress / total) * 100
            modfetch.log("debug", string.format("下载进度: %.1f%%", percent))
        end
    end

    return {
        success = true
    }
end

-- 下载完成后调用
function on_post_download(context)
    modfetch.log("info", "模组下载完成！")

    return {
        success = true
    }
end

-- 下载失败时调用
function on_download_failed(context)
    modfetch.log("error", "下载失败")

    return {
        success = false,
        error = "下载失败"
    }
end

-- 开始打包前调用
function on_pre_package(context)
    modfetch.log("info", "开始打包...")

    return {
        success = true
    }
end

-- 打包完成后调用
function on_post_package(context)
    modfetch.log("info", "打包完成！")

    return {
        success = true
    }
end
