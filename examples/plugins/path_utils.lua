--[[
    路径工具 Lua 插件示例

    演示如何使用路径处理 API。
--]]

plugin = {
    name = "path_utils",
    version = "1.0.0",
    description = "路径工具示例插件",
    author = "ModFetch Team"
}

function on_plugin_load(context)
    modfetch.log("info", "Path Utils 插件已加载")

    -- 演示路径操作
    local test_path = "/home/user/mods/example.jar"

    modfetch.log("debug", "原始路径: " .. test_path)
    modfetch.log("debug", "目录名: " .. modfetch.path_dirname(test_path))
    modfetch.log("debug", "文件名: " .. modfetch.path_basename(test_path))
    modfetch.log("debug", "扩展名: " .. modfetch.path_ext(test_path))

    -- 路径拼接
    local joined = modfetch.path_join("/home/user", "mods", "test.jar")
    modfetch.log("debug", "拼接路径: " .. joined)

    -- URL 操作
    local url = "https://cdn.modrinth.com/data/abc123/versions/1.0.0/mod.jar"
    local parsed = modfetch.url_parse(url)

    modfetch.log("debug", "URL 解析:")
    modfetch.log("debug", "  Scheme: " .. parsed.scheme)
    modfetch.log("debug", "  Host: " .. parsed.netloc)
    modfetch.log("debug", "  Path: " .. parsed.path)

    -- URL 编码/解码
    local text = "Hello World! 你好世界！"
    local encoded = modfetch.url_encode(text)
    local decoded = modfetch.url_decode(encoded)

    modfetch.log("debug", "URL 编码: " .. encoded)
    modfetch.log("debug", "URL 解码: " .. decoded)

    -- URL 拼接
    local base = "https://api.modrinth.com/v2/"
    local endpoint = "project/sodium"
    local full_url = modfetch.url_join(base, endpoint)

    modfetch.log("debug", "完整 URL: " .. full_url)

    return { success = true }
end

function on_config_loaded(context)
    -- 处理下载目录路径
    local download_dir = "./downloads"

    -- 确保目录存在
    if not modfetch.dir_exists(download_dir) then
        modfetch.dir_create(download_dir)
        modfetch.log("info", "创建下载目录: " .. download_dir)
    end

    -- 获取绝对路径
    local abs_path = modfetch.path_join(modfetch.dir_list(".")[1] or ".", download_dir)
    modfetch.log("info", "下载目录: " .. abs_path)

    return { success = true }
end

function on_post_download(context)
    local download_info = context.download_info

    if download_info and download_info.filename then
        local filename = download_info.filename

        -- 分析文件名
        modfetch.log("debug", "下载文件: " .. filename)
        modfetch.log("debug", "  目录: " .. modfetch.path_dirname(filename))
        modfetch.log("debug", "  名称: " .. modfetch.path_basename(filename))
        modfetch.log("debug", "  扩展名: " .. modfetch.path_ext(filename))

        -- 构建输出路径
        local output_dir = "./downloads"
        local output_path = modfetch.path_join(output_dir, modfetch.path_basename(filename))

        modfetch.log("debug", "输出路径: " .. output_path)
    end

    return { success = true }
end

function on_post_package(context)
    -- 处理打包输出路径
    local output_file = "./output/modpack.mrpack"

    -- 确保输出目录存在
    local output_dir = modfetch.path_dirname(output_file)
    if not modfetch.dir_exists(output_dir) then
        modfetch.dir_create(output_dir)
        modfetch.log("info", "创建输出目录: " .. output_dir)
    end

    modfetch.log("info", "打包文件: " .. output_file)

    return { success = true }
end

function on_plugin_unload(context)
    modfetch.log("info", "Path Utils 插件已卸载")
    return { success = true }
end
