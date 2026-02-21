--[[
    HTTP 客户端 Lua 插件示例

    演示如何使用 HTTP API 进行网络请求。
--]]

plugin = {
    name = "http_client",
    version = "1.0.0",
    description = "HTTP 客户端示例插件",
    author = "ModFetch Team"
}

-- Webhook URL（可以从配置中读取）
local webhook_url = nil

function on_plugin_load(context)
    modfetch.log("info", "HTTP Client 插件已加载")

    -- 从配置中读取 webhook URL
    webhook_url = plugin_config.webhook_url
    if webhook_url then
        modfetch.log("info", "Webhook URL: " .. webhook_url)
    end

    return { success = true }
end

function on_config_loaded(context)
    modfetch.log("info", "HTTP Client: 配置已加载")

    -- 示例：发送配置信息到远程服务器
    if webhook_url then
        local data = {
            event = "config_loaded",
            timestamp = modfetch.time_now(),
            minecraft_version = context.config.minecraft_version,
            mod_loader = context.config.mod_loader,
            mods_count = context.config.mods_count
        }

        -- 注意：http_post 是异步函数，这里简化处理
        -- 实际使用时可能需要处理异步结果
        modfetch.log("debug", "准备发送配置信息到 webhook")
    end

    return { success = true }
end

function on_pre_resolve(context)
    modfetch.log("info", "HTTP Client: 开始解析模组")

    -- 示例：获取 Modrinth API 信息
    -- 注意：这只是一个示例，实际 API 调用可能需要认证
    local api_url = "https://api.modrinth.com/v2/"
    modfetch.log("debug", "Modrinth API: " .. api_url)

    return { success = true }
end

function on_post_download(context)
    local mod_entry = context.mod_entry

    if mod_entry and webhook_url then
        -- 发送下载完成通知
        local data = {
            event = "mod_downloaded",
            timestamp = modfetch.time_now(),
            mod = {
                id = mod_entry.id,
                name = mod_entry.name,
                version = mod_entry.version
            }
        }

        modfetch.log("debug", "发送下载通知: " .. modfetch.json_encode(data))
    end

    return { success = true }
end

function on_download_failed(context)
    local mod_entry = context.mod_entry

    if mod_entry and webhook_url then
        -- 发送下载失败通知
        local data = {
            event = "mod_download_failed",
            timestamp = modfetch.time_now(),
            mod = {
                id = mod_entry.id,
                name = mod_entry.name
            }
        }

        modfetch.log("error", "下载失败通知: " .. modfetch.json_encode(data))
    end

    return { success = true }
end

function on_post_package(context)
    modfetch.log("info", "HTTP Client: 打包完成")

    if webhook_url then
        -- 发送打包完成通知
        local data = {
            event = "package_complete",
            timestamp = modfetch.time_now(),
            message = "Modpack 打包完成"
        }

        modfetch.log("info", "发送打包完成通知")
    end

    return { success = true }
end

function on_plugin_unload(context)
    modfetch.log("info", "HTTP Client 插件已卸载")
    return { success = true }
end
