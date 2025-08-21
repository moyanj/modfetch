import asyncio
import copy
import hashlib
import os
import json
import toml
import yaml
import shutil
from collections.abc import Mapping
import traceback
from typing import Optional, Dict, Any, Union, List

import aiofiles
import aiohttp

from modfetch.api import Client
from modfetch.error import ModFetchError


def should_include(entry: Union[Dict, str], version: str, features: List[str]) -> bool:
    """
    判断该项目是否应包含在当前构建中，基于 only_version 和 feature
    """
    if isinstance(entry, dict):
        if (need_ver := entry.get("only_version")) and need_ver != version:
            return False
        if (feature := entry.get("feature")) and feature not in features:
            return False
    return True


async def enqueue_file(
    fetcher: "ModFetch",
    url: str,
    filename: str,
    category: str,
    sha1: Optional[str] = None,
):
    """
    将文件加入下载队列，并确保目标路径存在
    """
    await fetcher.ensure_directory_exists(category)
    fetcher.download_queue.put_nowait(
        (url, filename, fetcher.get_download_path(category), sha1)
    )
    await fetcher.log("info", f"文件 '{filename}' 加入 {category} 下载队列。")


async def verify_sha1(
    fetcher: "ModFetch", file_path: str, expected_sha1: Optional[str]
) -> bool:
    """
    校验文件的 SHA1 是否匹配
    """
    if not expected_sha1:
        return True
    current_sha1 = await fetcher.calc_sha1(file_path)
    return current_sha1 == expected_sha1


class ModFetch:
    def __init__(self, config: dict, features: List[str]):
        self.api = Client()
        self.config = config
        self.mc_config = config["minecraft"]
        self.output_config = config.get("output", {})
        self.metadata = config.get("metadata", {})
        self.features = features
        self.download_queue = asyncio.Queue()
        self.processed_mods = set()
        self.failed_downloads = []
        self.skipped_mods = []
        self.max_concurrent = config.get("max_concurrent", 5)
        self.print_lock = asyncio.Lock()
        self.version_download_dir = ""

    async def ensure_directory_exists(self, category: str):
        """
        确保目标目录存在
        """
        path = self.get_download_path(category)
        os.makedirs(path, exist_ok=True)

    def get_download_path(self, category: str) -> str:
        """
        构建指定类别的下载路径（mods/resourcepacks/shaderpacks）
        """
        return os.path.join(self.version_download_dir, category)

    async def safe_print(self, message: str):
        """
        线程安全打印函数，防止并发日志混乱
        """
        async with self.print_lock:
            print(message)

    async def log(self, level: str, message: str):
        """
        日志处理函数，适配不同级别日志（info, warn, error）
        """
        level_tags = {
            "info": "",
            "success": "[完成]",
            "error": "[错误]",
            "warn": "[警告]",
            "skip": "[跳过]",
            "progress": "[进度]",
        }
        prefix = level_tags.get(level, "")
        await self.safe_print(f"{prefix} {message}")

    async def calc_sha1(self, file_path: str) -> Optional[str]:
        """
        计算文件的 SHA1 值
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
            return None

    async def copy_file(self, src_path: str, dest_path: str):
        """
        复制单个文件（支持文件和文件夹）
        """
        await self.log("info", f"文件 '{os.path.basename(src_path)}' 正在复制。")
        if os.path.isdir(src_path):
            shutil.copytree(src_path, dest_path)
        elif os.path.isfile(src_path):
            shutil.copy2(src_path, dest_path)
        else:
            raise ModFetchError("目录或文件不存在，无法复制。")
        await self.log("success", f"文件 '{os.path.basename(src_path)}' 复制完成。")

    async def download_file(
        self,
        url: str,
        filename: str,
        download_dir: str,
        expected_sha1: Optional[str] = None,
    ):
        """
        下载并校验目标文件
        """
        file_path = os.path.join(download_dir, filename)
        await self.log("info", f"开始下载: {filename}")

        if url.startswith("file://"):
            await self.copy_file(url[7:], file_path)
            return

        if os.path.exists(file_path) and await verify_sha1(
            self, file_path, expected_sha1
        ):
            await self.log(
                "skip", f"文件 '{filename}' 已存在，SHA1 校验成功，跳过下载。"
            )
            return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url, ssl=False) as response:
                    if response.status != 200:
                        await self.log(
                            "error", f"请求 {url} 时返回状态码 {response.status}"
                        )
                        self.failed_downloads.append(filename)
                        return

                    async with aiofiles.open(file_path, "wb") as f:
                        total_size = int(response.headers.get("Content-Length", 0))
                        downloaded = 0
                        last_percent = 0

                        await self.log(
                            "info", f"文件大小: {total_size / (1024 * 1024):.2f} MB"
                        )

                        async for chunk in response.content.iter_chunked(8192):
                            await f.write(chunk)
                            downloaded += len(chunk)

                            # 每隔大约5%显示进度
                            if total_size > 0:
                                percent = downloaded / total_size * 100
                                if percent - last_percent >= 5:
                                    await self.log(
                                        "progress", f"{filename}: {percent:.1f}%"
                                    )
                                    last_percent = percent

                        if total_size > 0 and downloaded == total_size:
                            await self.log("progress", f"{filename}: 100.0%")

            if not await verify_sha1(self, file_path, expected_sha1):
                os.remove(file_path)
                self.failed_downloads.append(filename)
                await self.log("error", f"{filename} SHA1 校验失败，重新下载。")
                return

            await self.log("success", f"文件 '{filename}' 下载完成。")
        except Exception as e:
            await self.log("error", f"下载 '{filename}' 出错: {e}")
            traceback.print_exc()
            if os.path.exists(file_path):
                os.remove(file_path)
            self.failed_downloads.append(filename)

    async def download_worker(self):
        """下载工作线程"""
        while not self.download_queue.empty():
            try:
                task = await self.download_queue.get()
                url, filename, download_path, sha1 = task
                await self.download_file(url, filename, download_path, sha1)
            except Exception as e:
                await self.log("error", f"下载任务执行失败: {e}")
            finally:
                self.download_queue.task_done()

    async def process_mod(self, project_info: dict, version: str):
        mod_id = project_info.get("id")
        if not mod_id or mod_id in self.processed_mods:
            return

        await self.log(
            "info",
            f"正在分析模组 '{project_info.get('slug', mod_id)}' (ID: {mod_id})。",
        )

        version_info, file_info = await self.api.get_version(
            mod_id, version, self.mc_config["mod_loader"]
        )

        if not version_info or not file_info:
            await self.log("skip", f"无法获取模组 {mod_id} 的版本或文件信息。")
            self.skipped_mods.append(f"{mod_id} - 无可用版本")
            return

        filename = file_info["filename"]
        url = file_info["url"]
        sha1 = file_info.get("hashes", {}).get("sha1")

        await enqueue_file(self, url, filename, "mods", sha1)
        self.processed_mods.add(mod_id)

        await self.process_dependencies(version_info, version)

    async def process_dependencies(self, version_info: dict, version: str):
        """
        处理当前文件的依赖项以避免重复逻辑
        """
        dependencies = version_info.get("dependencies", [])
        for dep in dependencies:
            dep_type = dep.get("dependency_type")
            dep_id = dep.get("project_id")

            if dep_type == "required" and dep_id and dep_id not in self.processed_mods:
                dep_info = await self.api.get_project(dep_id)
                if dep_info:
                    await self.log(
                        "info",
                        f"发现必需依赖: {dep_info.get('slug', dep_id)} (ID: {dep_id})",
                    )
                    await self.process_mod(dep_info, version)
                else:
                    await self.log("skip", f"无法解析必需依赖: {dep_id}")
                    self.skipped_mods.append(f"依赖: {dep_id} 无法获取信息")

    async def process_resourcepacks(self, project_info: dict, version: str):
        await self._process_content(project_info, version, "resourcepacks")

    async def process_shaderpacks(self, project_info: dict, version: str):
        await self._process_content(project_info, version, "shaderpacks")

    async def _process_content(self, project_info: dict, version: str, category: str):
        """
        将模组及其资源包统一处理的通用逻辑
        """
        mod_id = project_info.get("id")
        if not mod_id or mod_id in self.processed_mods:
            return

        await self.ensure_directory_exists(category)
        slug = project_info.get("slug", mod_id)
        await self.log("info", f"正在处理 {category} '{slug}' (ID: {mod_id})")

        version_info, file_info = await self.api.get_version(mod_id, version)
        if not version_info or not file_info:
            await self.log("skip", f"{category} '{slug}' 无可用版本，默认跳过")
            self.skipped_mods.append(f"{slug} - {version} 无可用资源")
            return

        await enqueue_file(
            self,
            file_info["url"],
            file_info["filename"],
            category,
            file_info.get("hashes", {}).get("version"),
        )
        await self.log("success", f"{category}: {slug} 已加入下载队列。")

    async def process_extra_urls(self, version: str):
        """
        下载额外的URL资源
        """
        extra_urls = self.mc_config.get("extra_urls", [])

        await self.log("info", "处理额外URL...")
        for entry in extra_urls:
            if not should_include(entry, version, self.features):
                await self.log("skip", f"链接 {entry} 被过滤，不适用于当前版本或功能")
                continue

            url = entry.get("url")
            filename = entry.get("filename", os.path.basename(url))
            file_type = entry.get("type", "file")

            if file_type not in ["mod", "file", "resourcepack", "shaderpack"]:
                await self.log("warn", f"忽略未知类型: {file_type}")
                continue

            await enqueue_file(
                self,
                url,
                filename,
                file_type.replace("pack", "packs"),
                entry.get("sha1"),
            )
            await self.log("success", f"额外URL {[url]} 已加入下载队列")

    async def version_process(self, version: str):
        await self.log(
            "info", f"准备下载目录 for {version}-{self.mc_config['mod_loader']}"
        )
        self.version_download_dir = os.path.join(
            self.output_config["download_dir"],
            f"{version}-{self.mc_config['mod_loader']}",
        )
        await self.setup_directories()
        await self.log("success", f"目录设定成功：{self.version_download_dir}")

        async def process_id(category):
            for idx in self.mc_config.get(category, []):
                if not should_include(idx, version, self.features):
                    await self.log(
                        "skip", f"{category} {idx} 不符合当前版本/特征要求。"
                    )
                    continue

                if isinstance(idx, dict):
                    idx = idx.get("id") or idx.get("slug")

                project_info = await self.api.get_project(idx)
                if not project_info:
                    await self.log("error", f"{idx} 未找到，跳过。")
                    self.skipped_mods.append(f"{category} {idx} - 找不到项目详情")
                    continue

                mod_id = project_info["id"]
                if mod_id in self.processed_mods:
                    continue

                if category == "mods":
                    await self.process_mod(project_info, version)
                elif category == "resourcepacks":
                    await self.process_resourcepacks(project_info, version)
                elif category == "shaderpacks":
                    await self.process_shaderpacks(project_info, version)

        await asyncio.gather(
            process_id("mods"),
            process_id("resourcepacks"),
            process_id("shaderpacks"),
        )

    async def setup_directories(self):
        await self.ensure_directory_exists("mods")
        await self.ensure_directory_exists("resourcepacks")
        await self.ensure_directory_exists("shaderpacks")

    async def download_loop(self):
        await self.log("success", f"启动下载 ({self.max_concurrent}并发)")

        workers = [
            asyncio.create_task(self.download_worker(), name=f"downloader-{i + 1}")
            for i in range(self.max_concurrent)
        ]

        await self.download_queue.join()
        for worker in workers:
            worker.cancel()
        await asyncio.gather(*workers, return_exceptions=True)

    def validate_config(self):
        mc = self.mc_config
        if not mc.get("version"):
            raise ModFetchError("请配置 Minecraft 1.0.0 以上版本")
        if not mc.get("mod_loader") or mc["mod_loader"] not in [
            "forge",
            "fabric",
            "quilt",
        ]:
            raise ModFetchError("mod_loader 必须为 forge/fabric/quilt")
        if not mc.get("mods", []):
            raise ModFetchError("请配置至少一个 mod 列表")

    async def analyze_config(self, config: dict):
        while parent_ref := config.get("from"):
            url = parent_ref.pop("url", None)
            fmt = parent_ref.pop("format", "json")
            if not url:
                await self.safe_print("未提供 from 配置文件地址")
                break

            text = await self.handle_url_content(url)
            await self.log("info", f"加载到父配置 {url}")
            parent_config = await self.parse_config(text, fmt)

            await self.analyze_config(parent_config)
            config = deep_merge(parent_config, config)

        self.config = config
        self.mc_config = config["minecraft"]
        self.output_config = config["output"]
        return config

    async def handle_url_content(self, url: str):
        if url.startswith("file://"):
            async with aiofiles.open(url[7:], "r") as f:
                return await f.read()
        async with self.api.session.get(url) as r:
            return await r.text()

    async def parse_config(self, text: str, fmt: str) -> dict[str, Any]:
        if fmt == "json":
            return json.loads(text)
        elif fmt == "toml":
            return toml.loads(text)
        elif fmt == "yaml":
            return yaml.safe_load(text)
        else:
            raise ModFetchError(f"未知的配置格式: {fmt}")

    async def make_mrpack(self, dir_path: str, mc_version: str):
        await self.log("info", f"生成 MrPack 创建整合包 for {mc_version}")
        mod_loader = self.mc_config["mod_loader"]
        try:
            if mod_loader == "fabric":
                loader_version = await self.api.get_fabric_version(mc_version)
            elif mod_loader == "quilt":
                loader_version = await self.api.get_quilt_version(mc_version)
            elif mod_loader == "forge":
                loader_version = await self.api.get_forge_version(mc_version)
            else:
                loader_version = None
        except Exception as e:
            await self.log("warn", f"无法获取加载器版本: {e}")
            loader_version = "unknown"

        manifest = {
            "game": "minecraft",
            "formatVersion": 1,
            "versionId": self.metadata.get("version", "1.0.0"),
            "name": self.metadata.get(
                "name", f"MyPack {self.mc_config.get('version')}"
            ),
            "summary": self.metadata.get("description", ""),
            "dependencies": {
                "minecraft": mc_version,
                f"{mod_loader}-loader": loader_version,
            },
            "files": [],
        }

        await self.build_mrpack_dir(os.path.join(dir_path, "overrides"), manifest)

    async def build_mrpack_dir(self, overrides_path: str, manifest: dict):
        os.makedirs(overrides_path, exist_ok=True)
        for root, _, files in os.walk(os.path.dirname(overrides_path)):
            relative = os.path.relpath(root, os.path.dirname(overrides_path))
            for file in files:
                shutil.copy2(
                    os.path.join(root, file),
                    os.path.join(overrides_path, os.path.basename(relative)),
                )
        await self.build_mrpack_final(overrides_path, manifest)

    async def build_mrpack_final(self, overrides_path: str, manifest: dict):
        manifest_path = os.path.join(overrides_path, "modrinth.index.json")
        async with aiofiles.open(manifest_path, "w", encoding="utf-8") as f:
            await f.write(json.dumps(manifest, indent=4))

        zip_file = os.path.join(
            self.output_config["download_dir"],
            f"{manifest['name']}-{manifest['versionId']}-MC{manifest['dependencies']['minecraft']}",
        )
        shutil.make_archive(zip_file, "zip", overrides_path)
        os.rename(zip_file + ".zip", zip_file + ".mrpack")
        shutil.rmtree(os.path.dirname(overrides_path))
        await self.log("success", f"MrPack 文件生成成功: {zip_file}.mrpack")

    async def start(self):
        await self.safe_print("开始 ModFetch 下载任务...")
        try:
            self.validate_config()
            await self.analyze_config(self.config)
            for version in self.mc_config["version"]:
                await self.version_process(version)

            await self.download_loop()

            if "zip" in self.output_config["format"]:
                for version in self.mc_config["version"]:
                    await self.compress_mods(version)
            if "mrpack" in self.output_config["format"]:
                await self.build_mrpack_dirs()
        finally:
            await self.api.close()

    async def build_mrpack_dirs(self):
        tasks = [
            self.make_mrpack(os.path.join(self.version_download_dir, v), v)
            for v in self.mc_config["version"]
        ]
        await asyncio.gather(*tasks)

    async def compress_mods(self, version):
        shutil.make_archive(
            f"{self.output_config["download_dir"]}/archive-{version}-{self.mc_config["mod_loader"]}",
            "zip",
            os.path.join(
                self.output_config["download_dir"],
                f"{version}-{self.mc_config["mod_loader"]}",
            ),
        )
        await self.log("success", "所有模组归档完成。")


class ModFetchError(Exception):
    """自定义异常类"""

    pass


async def compress_mods(output_path):
    for root, dirs, _ in os.walk(output_path):
        for d in dirs:
            p = os.path.join(root, d)
            if os.path.isdir(p):
                shutil.make_archive(p, "zip", p)
                await asyncio.sleep(0.01)  # 防止压栈阻塞主线程


def deep_merge(base: Mapping, merge: Mapping) -> dict:
    """
    合并两个配置字典，deep-merge 并列表去重
    """
    merged = copy.deepcopy(base)

    for key, merge_val in merge.items():
        base_val = merged.get(key)

        if isinstance(base_val, Mapping) and isinstance(merge_val, Mapping):
            merged[key] = deep_merge(base_val, merge_val)

        elif isinstance(base_val, list) and isinstance(merge_val, list):
            combined = base_val + merge_val
            merged[key] = list(dict.fromkeys(combined))  # 保留唯一性
        else:
            merged[key] = copy.deepcopy(merge_val)

    return merged
