--[[
    时间工具 Lua 插件示例

    演示如何使用时间处理 API。
--]]

plugin = {
    name = "time_utils",
    version = "1.0.0",
    description = "时间工具示例插件",
    author = "ModFetch Team"
}

-- 记录开始时间
local start_time = 0
local stage_times = {}

function on_plugin_load(context)
    modfetch.log("info", "Time Utils 插件已加载")

    -- 记录插件加载时间
    start_time = modfetch.time_now()

    -- 演示时间格式化
    local now = modfetch.time_now()
    modfetch.log("debug", "当前时间戳: " .. tostring(now))
    modfetch.log("debug", "默认格式: " .. modfetch.time_format(now))
    modfetch.log("debug", "日期格式: " .. modfetch.time_format(now, "%Y-%m-%d"))
    modfetch.log("debug", "时间格式: " .. modfetch.time_format(now, "%H:%M:%S"))
    modfetch.log("debug", "完整格式: " .. modfetch.time_format(now, "%Y年%m月%d日 %H:%M:%S"))

    return { success = true }
end

function on_config_loaded(context)
    -- 记录配置加载时间
    stage_times.config_loaded = modfetch.time_now()

    local elapsed = stage_times.config_loaded - start_time
    modfetch.log("info", "配置加载耗时: " .. string.format("%.3f", elapsed) .. " 秒")

    return { success = true }
end

function on_pre_resolve(context)
    -- 记录开始解析时间
    stage_times.pre_resolve = modfetch.time_now()

    return { success = true }
end

function on_post_resolve(context)
    -- 记录解析完成时间
    stage_times.post_resolve = modfetch.time_now()

    local elapsed = stage_times.post_resolve - stage_times.pre_resolve
    modfetch.log("info", "模组解析耗时: " .. string.format("%.3f", elapsed) .. " 秒")

    return { success = true }
end

function on_pre_download(context)
    -- 记录开始下载时间
    if not stage_times.pre_download then
        stage_times.pre_download = modfetch.time_now()
    end

    return { success = true }
end

function on_download_progress(context)
    local download_info = context.download_info

    if download_info then
        local progress = download_info.progress or 0
        local total = download_info.total or 0

        if total > 0 and progress > 0 then
            local elapsed = modfetch.time_now() - (stage_times.pre_download or modfetch.time_now())
            local speed = progress / elapsed
            local remaining = (total - progress) / speed

            modfetch.log("debug", string.format(
                "下载速度: %.2f KB/s, 预计剩余: %.1f 秒",
                speed / 1024,
                remaining
            ))
        end
    end

    return { success = true }
end

function on_post_download(context)
    -- 记录单个下载完成时间
    local now = modfetch.time_now()

    if stage_times.pre_download then
        local elapsed = now - stage_times.pre_download
        modfetch.log("debug", "本次下载耗时: " .. string.format("%.3f", elapsed) .. " 秒")
    end

    return { success = true }
end

function on_pre_package(context)
    -- 记录开始打包时间
    stage_times.pre_package = modfetch.time_now()

    return { success = true }
end

function on_post_package(context)
    -- 记录打包完成时间
    stage_times.post_package = modfetch.time_now()

    local elapsed = stage_times.post_package - stage_times.pre_package
    modfetch.log("info", "打包耗时: " .. string.format("%.3f", elapsed) .. " 秒")

    -- 输出完整时间报告
    local total_elapsed = stage_times.post_package - start_time
    modfetch.log("info", "========== 时间统计 ==========")
    modfetch.log("info", "总耗时: " .. string.format("%.3f", total_elapsed) .. " 秒")

    if stage_times.config_loaded then
        modfetch.log("info", "配置加载: " .. string.format("%.3f", stage_times.config_loaded - start_time) .. " 秒")
    end

    if stage_times.post_resolve and stage_times.pre_resolve then
        modfetch.log("info", "模组解析: " .. string.format("%.3f", stage_times.post_resolve - stage_times.pre_resolve) .. " 秒")
    end

    if stage_times.post_package and stage_times.pre_package then
        modfetch.log("info", "打包: " .. string.format("%.3f", stage_times.post_package - stage_times.pre_package) .. " 秒")
    end

    modfetch.log("info", "==============================")

    return { success = true }
end

function on_plugin_unload(context)
    local total_elapsed = modfetch.time_now() - start_time
    modfetch.log("info", "插件总运行时间: " .. string.format("%.3f", total_elapsed) .. " 秒")

    return { success = true }
end
