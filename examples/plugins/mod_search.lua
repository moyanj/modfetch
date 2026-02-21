--[[
    模组搜索 Lua 插件示例

    演示如何使用 Modrinth API 搜索模组。
--]]

plugin = {
    name = "mod_search",
    version = "1.0.0",
    description = "模组搜索示例插件",
    author = "ModFetch Team"
}

-- 搜索关键词列表
local search_keywords = {}

function on_plugin_load(context)
    modfetch.log("info", "Mod Search 插件已加载")

    -- 从配置中读取搜索关键词
    search_keywords = plugin_config.search_keywords or {}

    if #search_keywords > 0 then
        modfetch.log("info", "配置的关键词: " .. modfetch.json_encode(search_keywords))
    end

    return { success = true }
end

function on_config_loaded(context)
    modfetch.log("info", "Mod Search: 配置已加载")

    -- 获取所有模组
    local mods = modfetch.config.get_mods()

    -- 提取模组 ID 作为搜索关键词
    for _, mod in ipairs(mods) do
        if mod.id then
            table.insert(search_keywords, mod.id)
        elseif mod.slug then
            table.insert(search_keywords, mod.slug)
        end
    end

    modfetch.log("info", "共有 " .. tostring(#search_keywords) .. " 个搜索关键词")

    return { success = true }
end

function on_pre_resolve(context)
    modfetch.log("info", "Mod Search: 准备搜索模组信息")

    -- 注意：实际的搜索调用是异步的，需要在支持异步的环境中使用
    -- 这里仅作示例展示如何调用

    for i, keyword in ipairs(search_keywords) do
        if i > 3 then
            modfetch.log("debug", "... 还有 " .. tostring(#search_keywords - 3) .. " 个关键词")
            break
        end

        modfetch.log("debug", "准备搜索: " .. keyword)

        -- 示例：搜索模组（需要在支持异步的 Hook 中使用）
        -- local result = modfetch.modrinth.search(keyword, nil, 5)
        -- if result.success then
        --     modfetch.log("info", "找到 " .. tostring(result.total) .. " 个结果")
        --     for _, hit in ipairs(result.hits) do
        --         modfetch.log("debug", "  - " .. hit.title .. " (" .. hit.project_id .. ")")
        --     end
        -- end
    end

    return { success = true }
end

function on_post_resolve(context)
    modfetch.log("info", "Mod Search: 解析完成")
    return { success = true }
end

function on_post_package(context)
    modfetch.log("info", "Mod Search: 打包完成")
    return { success = true }
end

function on_plugin_unload(context)
    modfetch.log("info", "Mod Search 插件已卸载")
    return { success = true }
end
