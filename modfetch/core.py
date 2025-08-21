import asyncio
import copy
import hashlib
import json
import os
import shutil
import traceback
from collections.abc import Mapping, Sequence
from typing import Optional

import aiofiles
import aiohttp

from modfetch.api import Client
from modfetch.error import ModFetchError


class ModFetch:
    def __init__(self, config: dict):
        self.api = Client()
        self.config = config
        self.mc_config = config["minecraft"]
        self.output_config = config["output"]
        self.metadata = config.get("metadata", {})
        self.download_queue = asyncio.Queue()
        self.processed_mods = set()
        self.failed_downloads = []
        self.skipped_mods = []
        self.max_concurrent = config.get("max_concurrent", 5)  # 默认并发数
        if not isinstance(self.max_concurrent, int) or self.max_concurrent <= 0:
            print("[警告] max_concurrent 配置无效，将使用默认值 5。")
            self.max_concurrent = 5
        self.print_lock = asyncio.Lock()  # 输出锁防止日志交叉

    # 新增：安全的日志输出方法
    async def safe_print(self, message):
        async with self.print_lock:
            print(message)

    async def calc_sha1(self, file_path: str):
        """
        计算文件的SHA1值
        """
        sha1 = hashlib.sha1()
        try:
            async with aiofiles.open(file_path, "rb") as f:
                while True:
                    data = await f.read(4096)
                    if not data:
                        break
                    sha1.update(data)
            return sha1.hexdigest()
        except FileNotFoundError:
            return None  # 文件不存在时返回None，避免在验证时报错

    async def copy_file(self, src_path: str, dest_path: str):
        """
        复制单个文件 (支持并发)
        """
        await self.safe_print(f"[复制] 文件 '{os.path.basename(src_path)}' 开始复制。")
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dest_path)
            await self.safe_print(
                f"[复制] 文件 '{os.path.basename(src_path)}' 复制完成。"
            )
            return
        elif os.path.isfile(src_path):
            await self.safe_print(
                f"[复制] 文件 '{os.path.basename(src_path)}' 开始复制。"
            )
            shutil.copy2(src_path, dest_path)
            await self.safe_print(
                f"[复制] 文件 '{os.path.basename(src_path)}' 复制完成。"
            )
            return
        else:
            raise ModFetchError()

    async def download_file(
        self,
        url: str,
        filename: str,
        download_dir: str,
        expected_sha1: Optional[str] = None,
    ):
        """
        下载单个文件 (支持并发)
        """
        file_path = os.path.join(download_dir, filename)

        if url.startswith("file://"):
            # 本地文件，直接复制
            src_path = url[7:]
            if not os.path.exists(src_path):
                raise ModFetchError(f"文件 '{filename}' 不存在。")
            await self.copy_file(src_path, file_path)
            return

        if os.path.exists(file_path):
            current_sha1 = await self.calc_sha1(file_path)
            if expected_sha1 and current_sha1 == expected_sha1:
                await self.safe_print(f"[跳过] 文件 '{filename}' 已存在且SHA1匹配。")
                return
            elif expected_sha1 and current_sha1 != expected_sha1:
                await self.safe_print(
                    f"[警告] 文件 '{filename}' 已存在，但SHA1不匹配，将重新下载。"
                )
                os.remove(file_path)  # 删除旧文件以便重新下载
            else:
                await self.safe_print(f"[跳过] 文件 '{filename}' 已存在。")
                return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:  # 增加超时时间
                    if response.status != 200:
                        # 抛出AiohttpClientResponseError，ModFetchError会在except捕获
                        response.raise_for_status()

                    total_size = int(response.headers.get("content-length", 0))

                    # 简化多线程下载时的进度显示，避免进度条混乱
                    size_mb = total_size / (1024 * 1024) if total_size > 0 else 0
                    await self.safe_print(f"[下载] 开始: {filename} ({size_mb:.2f} MB)")

                    async with aiofiles.open(file_path, "wb") as f:
                        downloaded_size = 0
                        last_reported_progress = 0  # 记录上次报告的进度百分比

                        async for chunk in response.content.iter_chunked(
                            8192
                        ):  # 增加分块大小
                            if chunk:
                                await f.write(chunk)
                                downloaded_size += len(chunk)

                                # 每隔一定百分比（例如10%）或下载到一定大小（例如5MB）报告一次进度
                                if total_size > 0:
                                    current_progress_percent = (
                                        downloaded_size / total_size
                                    ) * 100
                                    if (
                                        current_progress_percent
                                        - last_reported_progress
                                        >= 5
                                    ):  # 每5%报告一次
                                        await self.safe_print(
                                            f"[进度] {filename}: {current_progress_percent:.1f}%"
                                        )
                                        last_reported_progress = (
                                            current_progress_percent
                                        )

                    # 确保下载完成时报告最终进度
                    if total_size > 0 and downloaded_size == total_size:
                        await self.safe_print(f"[进度] {filename}: 100.0%")

            # 下载完成后验证SHA1
            if expected_sha1:
                current_sha1 = await self.calc_sha1(file_path)
                if current_sha1 != expected_sha1:
                    os.remove(file_path)  # 删除损坏的文件
                    raise ModFetchError(f"文件 '{filename}' 下载后SHA1校验失败。")

            await self.safe_print(f"[完成] 文件 '{filename}' 下载成功。")
        except Exception as e:
            # 如果下载失败，删除可能已创建的不完整文件
            if os.path.exists(file_path):
                os.remove(file_path)
            self.failed_downloads.append(filename)  # 记录失败
            await self.safe_print(f"[错误] 下载文件 '{filename}' 时出错: {e}")
            # 不再重新抛出，而是记录并继续

    async def download_worker(self):
        """
        并发下载任务的工作线程
        """
        while True:
            try:
                # 从队列获取任务，设置一个较短的超时，当队列长时间为空时退出
                url, filename, download_dir, sha1 = await self.download_queue.get()
                await self.download_file(url, filename, download_dir, sha1)
                if self.download_queue.empty():
                    break
            except asyncio.CancelledError:
                # 任务被取消，退出循环 (用于关闭工作线程)
                break
            except Exception as e:
                await self.safe_print(f"[工作线程错误] 处理任务时发生意外: {e}")
            finally:
                # 每次处理完一个任务（无论成功失败）都要标记任务完成
                self.download_queue.task_done()

    async def process_mod(self, project_info: dict, version: str):
        mod_id = project_info.get("id")
        if mod_id in self.processed_mods or not mod_id:
            # await self.safe_print(f"[跳过] '{mod_id}' 已处理，跳过。")
            return

        mod_slug = project_info.get("slug") if project_info else mod_id

        await self.safe_print(f"[*] 正在分析模组: '{mod_slug}' (ID: {mod_id})")

        version_info, file_info = await self.api.get_version(
            mod_id, version, self.mc_config["mod_loader"]
        )

        if not version_info or not file_info:
            await self.safe_print(
                f"[跳过] 无法获取模组 '{mod_slug}' 的版本信息或文件，跳过。"
            )
            self.skipped_mods.append(
                f"{mod_slug} (ID: {mod_id}) - 在 {version} 无可用版本"
            )
            return

        filename = file_info["filename"]
        url = file_info["url"]
        sha1 = file_info.get("hashes", {}).get("sha1")

        await self.download_queue.put(
            (url, filename, self.version_download_dir + "/mods", sha1)
        )
        self.processed_mods.add(mod_id)
        await self.safe_print(
            f"    - '{mod_slug}' (版本: {version_info['version_number']}) 已加入下载队列。"
        )

        dependencies = version_info.get("dependencies", [])
        for dep in dependencies:
            dep_type = dep.get("dependency_type")
            dep_project_id = dep.get("project_id")

            if dep_type == "required" and dep_project_id:
                if dep_project_id not in self.processed_mods:
                    dep_project = await self.api.get_project(dep_project_id)
                    if dep_project:
                        dep_slug = dep_project["slug"]
                        await self.safe_print(
                            f"    - 发现必需依赖: '{dep_slug}' (ID: {dep_project_id})"
                        )
                        await self.process_mod(dep_project, version)  # 递归处理依赖项
                    else:
                        await self.safe_print(
                            f"[警告] 无法获取必需依赖 '{dep_project_id}' 的详情。"
                        )
                        self.skipped_mods.append(
                            f"依赖 {dep_project_id} - 无法获取详情"
                        )
                # else:  # 根据需要决定是否打印已处理的依赖跳过信息
                # await self.safe_print(f"    - 依赖 '{dep_project_id}' 已处理过，跳过。")

    async def process_extra_urls(self, version):
        for extar_url in self.mc_config.get("extra_urls", []):
            if isinstance(extar_url, str):
                url = extar_url
                type = "file"
                filename = None

            elif isinstance(extar_url, dict):
                if need_ver := extar_url.get("only_version"):
                    if need_ver != version:
                        continue

                type = extar_url.get("type", "file")
                if type not in ["mod", "file", "resourcepack", "shaderpack"]:
                    await self.safe_print(
                        f"[警告] 忽略未知的额外URL类型: {type}，请检查配置文件。"
                    )
                url = extar_url["url"]
                filename = extar_url.get("filename")
            else:
                print(f"[警告] 忽略无效的额外URL配置: {extar_url}")
                continue

            url = url.format(mc_version=version, loader=self.mc_config["mod_loader"])
            filename = filename or os.path.basename(url)

            download_path = ""
            if type == "file":
                download_path = self.version_download_dir
            elif type == "mod":
                download_path = self.version_download_dir + "/mods"
            elif type == "resourcepack":
                download_path = self.version_download_dir + "/resourcepacks"
            elif type == "shaderpack":
                download_path = self.version_download_dir + "/shaderpacks"

            await self.safe_print(f"[*] 添加额外URL: {url}")
            await self.download_queue.put((url, filename, download_path, None))

    async def process_shaderpacks(self, project_info, version):
        shaderpack_id = project_info["id"]
        mod_slug = project_info.get("slug") if project_info else shaderpack_id
        await self.safe_print(f"[*] 添加光影包: '{mod_slug}' (ID: {shaderpack_id})")

        version_info, file_info = await self.api.get_version(shaderpack_id, version)
        if not version_info or not file_info:
            await self.safe_print(
                f"[跳过] 无法获取资源包 '{mod_slug}' 的版本信息或文件，跳过。"
            )
            self.skipped_mods.append(
                f"{mod_slug} (ID: {shaderpack_id}) - 在 {version} 无可用版本"
            )
            return

        filename = file_info["filename"]
        url = file_info["url"]
        sha1 = file_info.get("hashes", {}).get("sha1")

        await self.download_queue.put(
            (url, filename, self.version_download_dir + "/shaderpacks", sha1)
        )

        await self.safe_print(
            f"    - '{mod_slug}' (版本: {version_info['version_number']}) 已加入下载队列。"
        )

    async def process_resourcepacks(self, project_info, version):
        resourcepack_id = project_info["id"]
        mod_slug = project_info.get("slug") if project_info else resourcepack_id
        await self.safe_print(f"[*] 添加资源包: '{mod_slug}' (ID: {resourcepack_id})")

        version_info, file_info = await self.api.get_version(resourcepack_id, version)
        if not version_info or not file_info:
            await self.safe_print(
                f"[跳过] 无法获取资源包 '{mod_slug}' 的版本信息或文件，跳过。"
            )
            self.skipped_mods.append(
                f"{mod_slug} (ID: {resourcepack_id}) - 在 {version} 无可用版本"
            )
            return

        filename = file_info["filename"]
        url = file_info["url"]
        sha1 = file_info.get("hashes", {}).get("sha1")

        await self.download_queue.put(
            (url, filename, self.version_download_dir + "/resourcepacks", sha1)
        )

        await self.safe_print(
            f"    - '{mod_slug}' (版本: {version_info['version_number']}) 已加入下载队列。"
        )

    async def version_process(self, version: str):
        """
        处理单个版本
        """
        self.version_download_dir = os.path.join(
            self.output_config["download_dir"],
            f"{version}-{self.mc_config['mod_loader']}",
        )
        os.makedirs(self.version_download_dir, exist_ok=True)
        await self.safe_print(
            f"\n正在为 Minecraft {version} ({self.mc_config['mod_loader']}) 准备下载目录: {self.version_download_dir}"
        )

        for mod_id in self.mc_config.get("mods", []):
            os.makedirs(self.version_download_dir + "/mods", exist_ok=True)
            project_info = await self.api.get_project(mod_id)
            if not project_info:
                await self.safe_print(f"[跳过] 无法找到模组: '{mod_id}'，跳过。")
                self.skipped_mods.append(f"未在 {version} 找到模组: {mod_id}")
                continue

            mod_id = project_info["id"]  # 使用ID进行内部处理

            await self.process_mod(project_info, version)

        for resourcepack_id in self.mc_config.get("resourcepacks", []):
            os.makedirs(self.version_download_dir + "/resourcepacks", exist_ok=True)
            project_info = await self.api.get_project(resourcepack_id)
            if not project_info:
                await self.safe_print(
                    f"[跳过] 无法找到资源包: '{resourcepack_id}'，跳过。"
                )
                self.skipped_mods.append(
                    f"未在 {version} 找到资源包: {resourcepack_id}"
                )
                continue
            await self.process_resourcepacks(project_info, version)

        for shaderpack_id in self.mc_config.get("shaderpacks", []):
            os.makedirs(self.version_download_dir + "/shaderpacks", exist_ok=True)
            project_info = await self.api.get_project(shaderpack_id)
            if not project_info:
                await self.safe_print(
                    f"[跳过] 无法找到光影包: '{shaderpack_id}'，跳过。"
                )
                self.skipped_mods.append(f"未在 {version} 找到光影包: {shaderpack_id}")
                continue
            await self.process_shaderpacks(project_info, version)

        await self.process_extra_urls(version)

    async def download_loop(self):
        """
        启动并发下载工作线程并等待所有任务完成
        """
        await self.safe_print(
            f"\n开始下载队列中的模组 (并发数: {self.max_concurrent})..."
        )

        # 创建并启动指定数量的下载工作线程
        tasks = []
        for i in range(self.max_concurrent):
            tasks.append(
                asyncio.create_task(
                    self.download_worker(), name=f"downloader-worker-{i+1}"
                )
            )

        # 等待下载队列中的所有任务都被处理完毕
        await self.download_queue.join()

        # 队列中的所有任务完成后，取消所有工作线程
        for task in tasks:
            task.cancel()

        # 等待所有工作线程实际结束
        await asyncio.gather(
            *tasks, return_exceptions=True
        )  # return_exceptions=True 避免由于 CancelledError 终止 gather

    def validate_config(self):
        """
        检查配置文件
        """
        if not self.mc_config.get("version"):
            raise ModFetchError("配置错误：请指定 'version'。")
        if not self.mc_config.get("mod_loader"):
            raise ModFetchError("配置错误：请指定 'mod_loader'。")
        if not self.mc_config.get("mods"):
            raise ModFetchError("配置错误：请指定 'mods'。")

        if self.mc_config["mod_loader"] not in ["forge", "fabric", "quilt"]:
            raise ModFetchError(
                "配置错误：'mod_loader' 只支持 'forge', 'fabric', 'quilt'。"
            )

        # 支持两种格式: ["a", "b"] 或 [{"slug": "a"}, {"id": "b"}]
        for idx, mod in enumerate(self.mc_config["mods"]):
            if isinstance(mod, str):
                continue  # 字符串格式直接接受
            elif isinstance(mod, dict) and (mod.get("slug") or mod.get("id")):
                continue  # 字典格式需要slug或id
            else:
                # 详细错误信息
                error_msg = f"配置错误：模组条目 #{idx+1} 应该是一个字符串或包含 'slug' 或 'id' 的字典"
                if isinstance(mod, dict):
                    error_msg += f"，但得到: {mod}"
                else:
                    error_msg += f"，但得到类型: {type(mod).__name__}"
                raise ModFetchError(error_msg)

    async def compress_mods(self):
        for dirx in os.listdir(self.output_config["download_dir"]):
            if not os.path.isdir(
                os.path.join(self.output_config["download_dir"], dirx)
            ):
                continue
            shutil.make_archive(
                dirx, "zip", os.path.join(self.output_config["download_dir"], dirx)
            )
            shutil.move(
                dirx + ".zip",
                os.path.join(self.output_config["download_dir"], dirx + ".zip"),
            )

    async def analyze_config(self, config: dict):
        """
        异步递归处理配置继承（deep_merge）
        如果 config 有 'from' 项，则加载父配置并合并到当前 config
        """
        while "from" in config:
            parent_url = config["from"].pop(
                "url", None
            )  # 一次性读取url并移除防止死循环
            file_format = config["from"].pop("format", "json")
            if not parent_url:
                await self.safe_print("[警告] 'from' 的 url 字段缺失，跳过继承。")
                break
            await self.safe_print(
                f"[继承] 正在加载父配置: {parent_url} (格式: {file_format})"
            )
            # 加载父配置（有可能已经是分析后的最终配置）
            parent_config = await self.api.get_config(parent_url, file_format)
            if not parent_config:
                await self.safe_print(
                    f"[致命错误] 无法加载父配置 '{parent_url}'。整合包无法继续。"
                )
                raise ModFetchError(
                    f"无法加载父配置 '{parent_url}'，可能是网络或格式问题"
                )
            # 递归分析父配置（处理其 from 字段）
            await self.analyze_config(parent_config)
            # 合并父配置和当前配置，以当前配置为主
            config = deep_merge(parent_config, config)
        return config

    async def make_mrpack(self, current_version_dir: str, mc_version: str):
        """
        生成整合包
        :param current_version_dir: 当前版本下载的根目录 (e.g., download/1.20.1-fabric)
        :param mc_version: Minecraft 版本
        """
        await self.safe_print(f"\n开始为 Minecraft {mc_version} 生成MrPack整合包...")

        pack_name = self.metadata.get("name", f"ModFetch Pack {mc_version}")
        pack_version = self.metadata.get("version", "1.0.0")
        pack_desc = self.metadata.get("description", "")
        mod_loader_id = self.mc_config["mod_loader"].lower()

        loader_version = "unknown"
        try:
            if mod_loader_id == "fabric":
                loader_version = await self.api.get_fabric_version(mc_version)
            elif mod_loader_id == "quilt":
                loader_version = await self.api.get_quilt_version(mc_version)
            elif mod_loader_id == "forge":
                loader_version = await self.api.get_forge_version(mc_version)
        except Exception as e:
            await self.safe_print(
                f"[警告] 无法获取 Mod 加载器版本信息: {e}. 将使用通用名称。"
            )

        manifest = {
            "game": "minecraft",
            "formatVersion": 1,
            "versionId": pack_version,
            "name": pack_name,
            "summary": pack_desc,
            "files": [],
            "dependencies": {
                "minecraft": mc_version,
                f"{mod_loader_id}-loader": loader_version,
            },
        }

        temp_pack_dir = os.path.join(
            self.output_config["download_dir"],
            f"ModPack_Temp_{mc_version}-{mod_loader_id}",
        )
        # Clean up any previous temp dir
        if os.path.exists(temp_pack_dir):
            shutil.rmtree(temp_pack_dir)
        os.makedirs(temp_pack_dir, exist_ok=True)

        overrides_dir = os.path.join(temp_pack_dir, "overrides")
        os.makedirs(overrides_dir, exist_ok=True)

        # Write manifest.json
        manifest_path = os.path.join(temp_pack_dir, "modrinth.index.json")
        async with aiofiles.open(manifest_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(manifest, indent=4))
        await self.safe_print(f"  - modrinth.index.json 已生成。")

        # Copy downloaded files to the overrides directory
        await self.safe_print(f"  - 正在将下载的文件复制到 overrides 文件夹...")
        for root, dirs, files in os.walk(current_version_dir):
            relative_path = os.path.relpath(root, current_version_dir)
            destination_dir = os.path.join(overrides_dir, relative_path)
            os.makedirs(destination_dir, exist_ok=True)
            for file in files:
                shutil.copy2(os.path.join(root, file), destination_dir)
        await self.safe_print(f"  - 文件复制完成。")

        # Create the zip archive
        zip_output_filename = os.path.join(
            self.output_config["download_dir"],
            f"{pack_name}_{pack_version}_MC{mc_version}-{mod_loader_id}",
        )
        shutil.make_archive(zip_output_filename, "zip", temp_pack_dir)
        shutil.move(
            zip_output_filename + ".zip",
            os.path.join(zip_output_filename + ".mrpack"),
        )
        await self.safe_print(
            f"[完成] 标准整合包 '{os.path.basename(zip_output_filename)}.mrpack' 已创建。"
        )

        # Clean up the temporary directory
        shutil.rmtree(temp_pack_dir)
        await self.safe_print(
            f"  - 临时目录 '{os.path.basename(temp_pack_dir)}' 已清理。"
        )

    async def start(self):
        try:
            self.validate_config()
            self.config = await self.analyze_config(self.config)
            self.mc_config = self.config["minecraft"]
            self.output_config = self.config["output"]
            self.metadata = self.config.get("metadata", {})
            print(self.config)
            await self.safe_print("--- ModFetch 下载器启动 ---")
            for version in self.mc_config["version"]:
                await self.safe_print(
                    f"\n正在分析 Minecraft 版本 {version} 的模组及其依赖..."
                )
                self.processed_mods.clear()  # 每个版本重新计算已处理模组
                await self.version_process(version)
                await self.safe_print(f"版本 {version} 的模组分析完毕。")

            # 统一执行下载
            await self.download_loop()

            if "zip" in self.output_config["format"]:
                await self.compress_mods()

            if "mrpack" in self.output_config["format"]:
                for version in self.mc_config["version"]:
                    await self.make_mrpack(
                        os.path.join(
                            self.output_config["download_dir"],
                            f"{version}-" + self.mc_config["mod_loader"],
                        ),
                        version,
                    )
            await self.api.close()
            await self.safe_print("\n--- ModFetch 所有任务完成 ---")

            if self.failed_downloads:
                await self.safe_print("\n以下文件下载失败：")
                for f in self.failed_downloads:
                    await self.safe_print(f"  - {f}")
            if self.skipped_mods:
                await self.safe_print("\n以下模组被跳过：")
                for m in self.skipped_mods:
                    await self.safe_print(f"  - {m}")
            if not self.failed_downloads and not self.skipped_mods:
                await self.safe_print("\n所有模组及其依赖都已成功处理并下载。")

        except ModFetchError as e:
            await self.safe_print(f"\n[致命错误] {e}")
        except Exception as e:
            await self.safe_print(f"\n[意外错误] 发生了一个未预期的错误: {e}")
            traceback.print_exc()
        finally:
            # 确保 session 关闭
            if not self.api.session.closed:
                await self.api.close()


def deep_merge(base: dict, merge: dict) -> dict:
    """
    Deep merge 两个字典，列表合并，并可选去重

    参数:
        base (dict): 默认/旧配置
        merge (dict): 需要合并的新配置
        deduplicate_lists (bool): 合并列表时是否去重（默认 True）

    返回:
        dict: 合并后的完整字典
    """
    merged = copy.deepcopy(base)  # 深度复制 base，避免修改原字典

    def merge_values(base_val, merge_val):
        # 如果 merge_val 是 dict 且 base_val 也是 dict，递归合并
        if isinstance(base_val, Mapping) and isinstance(merge_val, Mapping):
            return deep_merge(base_val, merge_val)  # type: ignore

        # 如果 merge_val 是 list 且 base_val 是 list，拼接并去重
        elif isinstance(base_val, list) and isinstance(merge_val, list):
            combined = base_val + merge_val
            # 保留顺序的去重方式（适用于 hashable 类型）
            seen = set()
            unique = []
            for item in combined:
                if item not in seen:
                    seen.add(item)
                    unique.append(item)
            return unique

        # 其他情况（包括 primitives, 不一致类型）直接用 merge_val 覆盖 base_val
        else:
            return merge_val

    for key, merge_val in merge.items():
        base_val = merged.get(key)
        if key in merged:
            # 如果 base_val 是 dict，而 merge_val 是 dict，递归合并
            # 如果 base_val 是 list，merge_val 是 list，就合并它们
            if isinstance(base_val, Mapping) and isinstance(merge_val, Mapping):
                merged[key] = deep_merge(base_val, merge_val)  # type: ignore
            elif isinstance(base_val, list) and isinstance(merge_val, list):
                merged[key] = base_val + merge_val
                seen = set()
                merged[key] = [
                    item
                    for item in merged[key]
                    if item not in seen and not seen.add(item)
                ]
            else:
                merged[key] = merge_val
        else:
            merged[key] = copy.deepcopy(merge_val)

    return merged
