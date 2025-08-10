from modfetch.modrinth_api import ModrinthClient
import os
from modfetch.error import ModFetchError
import aiohttp
from typing import Optional
import hashlib
from tqdm.auto import tqdm
import asyncio
import aiofiles


class ModFetch:
    def __init__(self, config: dict):
        self.api = ModrinthClient()
        self.config = config
        self.download_queue = asyncio.Queue()  # 改为asyncio.Queue以支持并发控制
        self.processed_mods = set()
        self.failed_downloads = []  # 新增：记录下载失败的文件
        self.skipped_mods = []  # 新增：记录跳过的模组

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

    async def download_file(
        self,
        url: str,
        filename: str,
        download_dir: str,
        expected_sha1: Optional[str] = None,
    ):
        """
        下载单个文件
        """
        file_path = os.path.join(download_dir, filename)

        if os.path.exists(file_path):
            current_sha1 = await self.calc_sha1(file_path)
            if expected_sha1 and current_sha1 == expected_sha1:
                print(f"[跳过] 文件 '{filename}' 已存在且SHA1匹配。")
                return
            elif expected_sha1 and current_sha1 != expected_sha1:
                print(f"[警告] 文件 '{filename}' 已存在，但SHA1不匹配，将重新下载。")
                os.remove(file_path)  # 删除旧文件以便重新下载
            else:
                print(f"[跳过] 文件 '{filename}' 已存在。")
                return

        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(url) as response:
                    if response.status != 200:
                        response.raise_for_status()  # 抛出AiohttpClientResponseError
                        # raise ModFetchError( # 如果需要自定义错误消息
                        #     f"下载文件 '{filename}' 失败，状态码 {response.status}"
                        # )

                    total_size = int(response.headers.get("content-length", 0))

                    # 使用 tqdm 创建进度条
                    with tqdm(
                        total=total_size,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=f"下载 {filename}",
                        miniters=1,  # 确保小文件也能显示进度
                        leave=False,  # 下载完成后不保留进度条
                    ) as progress_bar:
                        async with aiofiles.open(file_path, "wb") as f:
                            async for chunk in response.content.iter_chunked(4096):
                                if chunk:
                                    await f.write(chunk)
                                    progress_bar.update(len(chunk))

            # 下载完成后验证SHA1
            if expected_sha1:
                current_sha1 = await self.calc_sha1(file_path)
                if current_sha1 != expected_sha1:
                    os.remove(file_path)  # 删除损坏的文件
                    raise ModFetchError(f"文件 '{filename}' 下载后SHA1校验失败。")

            print(f"[完成] 文件 '{filename}' 下载成功。")
        except Exception as e:
            # 如果下载失败，删除可能已创建的不完整文件
            if os.path.exists(file_path):
                os.remove(file_path)
            self.failed_downloads.append(filename)  # 记录失败
            print(f"[错误] 下载文件 '{filename}' 时出错: {e}")
            # 不再重新抛出，而是记录并继续

    async def process_mod(self, mod_id: str, version: str):
        if mod_id in self.processed_mods:
            return

        project_info = await self.api.get_project(mod_id)
        mod_slug = project_info.get("slug") if project_info else mod_id

        print(f"[*] 正在分析模组: '{mod_slug}' (ID: {mod_id})")

        version_info, file_info = await self.api.get_version(
            mod_id, version, self.config["mod_loader"]
        )

        if not version_info or not file_info:
            print(f"[跳过] 无法获取模组 '{mod_slug}' 的版本信息或文件，跳过。")
            self.skipped_mods.append(f"{mod_slug} (ID: {mod_id}) - 无可用版本")
            return

        filename = file_info["filename"]
        url = file_info["url"]
        sha1 = file_info.get("hashes", {}).get("sha1")

        await self.download_queue.put((url, filename, self.version_download_dir, sha1))
        self.processed_mods.add(mod_id)
        print(
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
                        print(
                            f"    - 发现必需依赖: '{dep_slug}' (ID: {dep_project_id})"
                        )
                        await self.process_mod(
                            dep_project_id, version
                        )  # 递归处理依赖项
                    else:
                        print(f"[警告] 无法获取必需依赖 '{dep_project_id}' 的详情。")
                        self.skipped_mods.append(
                            f"依赖 {dep_project_id} - 无法获取详情"
                        )
                # else:  # 根据需要决定是否打印已处理的依赖跳过信息
                # print(f"    - 依赖 '{dep_project_id}' 已处理过，跳过。")

    async def version_process(self, version: str):
        """
        处理单个版本
        """
        self.version_download_dir = os.path.join(
            self.config["download_dir"], f"{version}-{self.config['mod_loader']}"
        )
        os.makedirs(self.version_download_dir, exist_ok=True)
        print(
            f"\n正在为 Minecraft {version} ({self.config['mod_loader']}) 准备下载目录: {self.version_download_dir}"
        )

        for mod_cfg in self.config["mods"]:
            # 支持两种配置格式：
            # 1. 字符串格式: "a"
            # 2. 字典格式: {"slug": "a"} 或 {"id": "b"}
            if isinstance(mod_cfg, str):
                mod_identifier = mod_cfg
            else:  # 字典格式
                mod_identifier = mod_cfg.get("id") or mod_cfg.get("slug")

            if not mod_identifier:
                print(f"[跳过] 模组条目缺少标识符: {mod_cfg}")
                self.skipped_mods.append(f"配置错误模组: {mod_cfg}")
                continue

            project_info = await self.api.get_project(mod_identifier)
            if not project_info:
                print(f"[跳过] 无法找到模组: '{mod_identifier}'，跳过。")
                self.skipped_mods.append(f"未找到模组: {mod_identifier}")
                continue

            mod_id = project_info["id"]  # 使用ID进行内部处理
            # mod_slug = project_info["slug"] # process_mod内部会获取并打印slug

            await self.process_mod(mod_id, version)

    async def download_loop(self):
        print(f"\n开始下载队列中的模组...")
        while not self.download_queue.empty():
            url, filename, download_dir, sha1 = await self.download_queue.get()
            await self.download_file(url, filename, download_dir, sha1)

        # 并发下载，限制并发数量（例如：5个）
        # await asyncio.gather(*tasks)  # 这里未限制并发，所有文件同时开始，tqdm会交叉显示

    def validate_config(self):
        """
        检查配置文件
        """
        if not self.config.get("mc_version"):
            raise ModFetchError("配置错误：请指定 'mc_version'。")
        if not self.config.get("mod_loader"):
            raise ModFetchError("配置错误：请指定 'mod_loader'。")
        if not self.config.get("download_dir"):
            raise ModFetchError("配置错误：请指定 'download_dir'。")
        if not self.config.get("mods"):
            raise ModFetchError("配置错误：请指定 'mods'。")

        if self.config["mod_loader"] not in ["forge", "fabric", "quilt"]:
            raise ModFetchError(
                "配置错误：'mod_loader' 只支持 'forge', 'fabric', 'quilt'。"
            )

        # 支持两种格式: ["a", "b"] 或 [{"slug": "a"}, {"id": "b"}]
        for idx, mod in enumerate(self.config["mods"]):
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

    async def start(self):
        try:
            self.validate_config()
            print("--- ModFetch 下载器启动 ---")
            for version in self.config["mc_version"]:
                print(f"\n正在分析 Minecraft 版本 {version} 的模组及其依赖...")
                self.processed_mods.clear()  # 每个版本重新计算已处理模组
                await self.version_process(version)
                print(f"版本 {version} 的模组分析完毕。")

            # 统一执行下载
            await self.download_loop()

            await self.api.close()
            print("\n--- ModFetch 所有任务完成 ---")

            if self.failed_downloads:
                print("\n以下文件下载失败：")
                for f in self.failed_downloads:
                    print(f"  - {f}")
            if self.skipped_mods:
                print("\n以下模组被跳过：")
                for m in self.skipped_mods:
                    print(f"  - {m}")
            if not self.failed_downloads and not self.skipped_mods:
                print("\n所有模组及其依赖都已成功处理并下载。")

        except ModFetchError as e:
            print(f"\n[致命错误] {e}")
        except Exception as e:
            print(f"\n[意外错误] 发生了一个未预期的错误: {e}")
        finally:
            # 确保 session 关闭
            if not self.api.session.closed:
                await self.api.close()
