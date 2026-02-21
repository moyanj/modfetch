--[[
    加密/哈希工具 Lua 插件示例

    演示如何使用哈希和编码 API。
--]]

plugin = {
    name = "crypto_utils",
    version = "1.0.0",
    description = "加密哈希工具示例插件",
    author = "ModFetch Team"
}

function on_plugin_load(context)
    modfetch.log("info", "Crypto Utils 插件已加载")

    -- 演示哈希函数
    local test_data = "Hello, ModFetch!"

    modfetch.log("debug", "原始数据: " .. test_data)
    modfetch.log("debug", "MD5: " .. modfetch.hash_md5(test_data))
    modfetch.log("debug", "SHA1: " .. modfetch.hash_sha1(test_data))
    modfetch.log("debug", "SHA256: " .. modfetch.hash_sha256(test_data))

    -- 演示 Base64 编码
    local encoded = modfetch.base64_encode(test_data)
    modfetch.log("debug", "Base64 编码: " .. encoded)

    local decoded = modfetch.base64_decode(encoded)
    modfetch.log("debug", "Base64 解码: " .. decoded)

    -- 生成 UUID
    local uuid = modfetch.uuid()
    modfetch.log("debug", "生成的 UUID: " .. uuid)

    return { success = true }
end

function on_config_loaded(context)
    -- 为配置生成唯一标识
    local config_hash = modfetch.hash_sha256(
        (context.config.minecraft_version or "") ..
        (context.config.mod_loader or "") ..
        tostring(context.config.mods_count or 0)
    )

    modfetch.log("info", "配置哈希: " .. string.sub(config_hash, 1, 16) .. "...")

    return { success = true }
end

function on_post_download(context)
    local download_info = context.download_info

    if download_info and download_info.filename then
        local filename = download_info.filename

        -- 计算文件名的哈希（实际文件内容哈希需要读取文件）
        local file_hash = modfetch.hash_sha256(filename)
        modfetch.log("debug", "文件 " .. filename .. " 的哈希: " .. string.sub(file_hash, 1, 8) .. "...")

        -- 验证 SHA1（如果提供）
        if download_info.sha1 then
            modfetch.log("debug", "提供的 SHA1: " .. download_info.sha1)
        end
    end

    return { success = true }
end

function on_post_package(context)
    -- 为打包结果生成标识
    local package_id = modfetch.uuid()
    modfetch.log("info", "包 ID: " .. package_id)

    -- 生成时间戳哈希
    local timestamp = modfetch.time_now()
    local time_hash = modfetch.hash_md5(tostring(timestamp))
    modfetch.log("debug", "时间戳哈希: " .. time_hash)

    return { success = true }
end

function on_plugin_unload(context)
    modfetch.log("info", "Crypto Utils 插件已卸载")
    return { success = true }
end
