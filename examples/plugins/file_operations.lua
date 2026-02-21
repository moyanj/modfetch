--[[
    文件操作 Lua 插件示例

    演示如何使用文件系统 API。
--]]

plugin = {
    name = "file_operations",
    version = "1.0.0",
    description = "文件操作示例插件",
    author = "ModFetch Team"
}

-- 输出目录
local output_dir = "./plugin_output"

function on_plugin_load(context)
    modfetch.log("info", "File Operations 插件已加载")

    -- 创建输出目录
    if not modfetch.dir_exists(output_dir) then
        modfetch.dir_create(output_dir)
        modfetch.log("info", "创建输出目录: " .. output_dir)
    end

    -- 写入插件启动日志
    local log_file = modfetch.path_join(output_dir, "plugin.log")
    local timestamp = modfetch.time_format(nil, "%Y-%m-%d %H:%M:%S")
    modfetch.file_append(log_file, "[" .. timestamp .. "] 插件已加载\n")

    return { success = true }
end

function on_config_loaded(context)
    -- 保存配置信息到文件
    local config_file = modfetch.path_join(output_dir, "config.json")
    local config_info = {
        minecraft_version = context.config.minecraft_version,
        mod_loader = context.config.mod_loader,
        mods_count = context.config.mods_count,
        timestamp = modfetch.time_now()
    }

    modfetch.file_write(config_file, modfetch.json_encode(config_info))
    modfetch.log("info", "配置已保存到: " .. config_file)

    return { success = true }
end

function on_pre_resolve(context)
    -- 创建解析记录文件
    local resolve_file = modfetch.path_join(output_dir, "resolve.log")
    modfetch.file_write(resolve_file, "开始解析模组...\n")

    return { success = true }
end

function on_post_resolve(context)
    -- 追加解析完成记录
    local resolve_file = modfetch.path_join(output_dir, "resolve.log")
    local timestamp = modfetch.time_format(nil, "%H:%M:%S")
    modfetch.file_append(resolve_file, "[" .. timestamp .. "] 解析完成\n")

    return { success = true }
end

function on_post_download(context)
    -- 记录下载的模组
    local download_file = modfetch.path_join(output_dir, "downloads.log")
    local mod_entry = context.mod_entry

    if mod_entry then
        local timestamp = modfetch.time_format(nil, "%H:%M:%S")
        local line = "[" .. timestamp .. "] " .. (mod_entry.name or mod_entry.id) .. "\n"
        modfetch.file_append(download_file, line)
    end

    return { success = true }
end

function on_post_package(context)
    -- 生成报告文件
    local report_file = modfetch.path_join(output_dir, "report.txt")

    local report = {
        "========== ModFetch 打包报告 ==========",
        "生成时间: " .. modfetch.time_format(),
        "", "输出目录内容:",
    }

    -- 列出输出目录中的所有文件
    local files = modfetch.dir_list(output_dir)
    for _, file in ipairs(files) do
        local basename = modfetch.path_basename(file)
        table.insert(report, "  - " .. basename)
    end

    table.insert(report, "")
    table.insert(report, "======================================")

    modfetch.file_write(report_file, table.concat(report, "\n"))
    modfetch.log("info", "报告已生成: " .. report_file)

    return { success = true }
end

function on_plugin_unload(context)
    -- 记录插件卸载
    local log_file = modfetch.path_join(output_dir, "plugin.log")
    local timestamp = modfetch.time_format(nil, "%Y-%m-%d %H:%M:%S")
    modfetch.file_append(log_file, "[" .. timestamp .. "] 插件已卸载\n")

    return { success = true }
end
