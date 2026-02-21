--[[
    字符串工具 Lua 插件示例

    演示如何使用字符串处理 API。
--]]

plugin = {
    name = "string_utils",
    version = "1.0.0",
    description = "字符串工具示例插件",
    author = "ModFetch Team"
}

function on_plugin_load(context)
    modfetch.log("info", "String Utils 插件已加载")

    -- 演示各种字符串操作
    local test_string = "  Hello, ModFetch World!  "

    modfetch.log("debug", "原始字符串: '" .. test_string .. "'")
    modfetch.log("debug", "trim: '" .. modfetch.trim(test_string) .. "'")
    modfetch.log("debug", "lower: '" .. modfetch.lower(test_string) .. "'")
    modfetch.log("debug", "upper: '" .. modfetch.upper(test_string) .. "'")

    -- 分割字符串
    local parts = modfetch.split("apple,banana,cherry", ",")
    modfetch.log("debug", "分割结果: " .. modfetch.json_encode(parts))

    -- 检查包含
    modfetch.log("debug", "包含 'ModFetch': " .. tostring(modfetch.contains(test_string, "ModFetch")))
    modfetch.log("debug", "以 'Hello' 开头: " .. tostring(modfetch.starts_with(modfetch.trim(test_string), "Hello")))
    modfetch.log("debug", "以 '!' 结尾: " .. tostring(modfetch.ends_with(modfetch.trim(test_string), "!")))

    -- 替换
    local replaced = modfetch.replace(test_string, "World", "Lua")
    modfetch.log("debug", "替换后: '" .. replaced .. "'")

    -- 子字符串
    local sub = modfetch.sub(test_string, 5, 15)
    modfetch.log("debug", "子字符串 [5:15]: '" .. sub .. "'")

    -- 正则匹配
    local match = modfetch.match("Version: 1.2.3", "%d+%.%d+%.%d+")
    modfetch.log("debug", "匹配版本号: " .. (match or "未找到"))

    local all_matches = modfetch.match_all("Files: a.txt, b.lua, c.py", "\\.%w+")
    modfetch.log("debug", "所有扩展名: " .. modfetch.json_encode(all_matches))

    return { success = true }
end

function on_config_loaded(context)
    -- 验证配置中的字符串
    local mc_version = context.config.minecraft_version or ""

    -- 检查版本格式
    if modfetch.match(mc_version, "^%d+%.%d+%.%d+$") then
        modfetch.log("info", "Minecraft 版本格式正确: " .. mc_version)
    elseif modfetch.match(mc_version, "^%d+%.%d+$") then
        modfetch.log("info", "Minecraft 版本格式正确: " .. mc_version)
    else
        modfetch.log("warning", "Minecraft 版本格式可能不正确: " .. mc_version)
    end

    -- 检查 mod_loader
    local loader = context.config.mod_loader or ""
    local valid_loaders = {"fabric", "forge", "neoforge", "quilt"}
    local is_valid = false

    for _, valid in ipairs(valid_loaders) do
        if modfetch.lower(loader) == valid then
            is_valid = true
            break
        end
    end

    if not is_valid then
        modfetch.log("warning", "未知的模组加载器: " .. loader)
    end

    return { success = true }
end

function on_pre_resolve(context)
    modfetch.log("info", "String Utils: 准备解析模组")
    return { success = true }
end

function on_post_resolve(context)
    local mod_entry = context.mod_entry

    if mod_entry then
        local mod_id = mod_entry.id or ""
        local mod_name = mod_entry.name or ""

        -- 检查模组 ID 格式
        if modfetch.match(mod_id, "^[a-z][a-z0-9_-]*$") then
            modfetch.log("debug", "模组 ID 格式正确: " .. mod_id)
        else
            modfetch.log("warning", "模组 ID 格式可能不规范: " .. mod_id)
        end

        -- 处理模组名称
        if mod_name and #mod_name > 0 then
            -- 清理名称
            local clean_name = modfetch.trim(mod_name)
            clean_name = modfetch.replace(clean_name, "  ", " ")
            modfetch.log("debug", "清理后的模组名称: " .. clean_name)
        end
    end

    return { success = true }
end

function on_post_download(context)
    local download_info = context.download_info

    if download_info then
        local filename = download_info.filename or ""

        -- 提取文件扩展名
        local ext = modfetch.match(filename, "\\.[^.]+$")
        if ext then
            modfetch.log("debug", "文件扩展名: " .. ext)
        end

        -- 检查是否是 jar 文件
        if modfetch.ends_with(modfetch.lower(filename), ".jar") then
            modfetch.log("debug", "确认是 JAR 文件: " .. filename)
        end
    end

    return { success = true }
end

function on_plugin_unload(context)
    modfetch.log("info", "String Utils 插件已卸载")
    return { success = true }
end
