from modfetch.modrinth_api import ModrinthClient
import os
from modfetch.error import ModFetchError
import aiohttp
from typing import Optional
import hashlib
from tqdm import tqdm
import asyncio


class ModFetch:
    def __init__(self, config: dict):
        self.api = ModrinthClient()
        self.config = config
        self.download_queue = set()
        self.processed_mods = set()

    def calc_sha1(self, file_path: str):
        """
        计算文件的SHA1值
        """
        sha1 = hashlib.sha1()
        with open(file_path, "rb") as f:
            while True:
                data = f.read(4096)
                if not data:
                    break
                sha1.update(data)
        return sha1.hexdigest()

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
            if expected_sha1:
                if self.calc_sha1(file_path) == expected_sha1:
                    print(f"文件 {filename} 已存在，跳过下载")
                    return
                else:
                    print(f"文件 {filename} 已存在，但 SHA1 不匹配，重新下载")
            else:
                print(f"文件 {filename} 已存在，跳过下载")
                return

        try:
            async with aiohttp.ClientSession() as session:
                response = await session.get(url)
                if response.status != 200:
                    raise ModFetchError(
                        f"下载文件 {filename} 失败，状态码 {response.status}"
                    )

                # 获取文件总大小
                total_size = int(response.headers.get("content-length", 0))

                # 使用 tqdm 创建进度条
                with open(file_path, "wb") as f:
                    with tqdm(
                        total=total_size,
                        unit="B",
                        unit_scale=True,
                        unit_divisor=1024,
                        desc=filename,
                    ) as progress_bar:
                        async for chunk in response.content.iter_chunked(4096):
                            if chunk:
                                f.write(chunk)
                                progress_bar.update(len(chunk))

                # 下载完成后验证SHA1
                if expected_sha1:
                    if self.calc_sha1(file_path) != expected_sha1:
                        os.remove(file_path)  # 删除损坏的文件
                        raise ModFetchError(f"文件 {filename} 下载后SHA1校验失败")
                print(f"文件 {filename} 下载完成")
        except Exception as e:
            # 如果下载失败，删除可能已创建的不完整文件
            if os.path.exists(file_path):
                os.remove(file_path)
            raise ModFetchError(f"下载文件 {filename} 时出错: {str(e)}")

    async def process_mod(self, mod_id: str, version: str):
        if mod_id in self.processed_mods:
            return

        # 获取项目信息以获取slug用于显示
        project_info = await self.api.get_project(mod_id)
        mod_slug = project_info.get("slug") if project_info else mod_id
        print(f"正在处理模组: {mod_slug} (ID: {mod_id})")

        version_info, file_info = await self.api.get_version(
            mod_id, version, self.config["mod_loader"]
        )

        if not version_info or not file_info:
            print(f"无法获取模组 {mod_slug} 的版本信息，跳过")
            return

        # 获取文件名和下载URL
        filename = file_info["filename"]
        url = file_info["url"]
        # 获取SHA1值用于验证
        sha1 = file_info.get("hashes", {}).get("sha1")

        # 添加到下载队列
        self.download_queue.add((url, filename, self.version_download_dir, sha1))
        self.processed_mods.add(mod_id)

        dependencies = version_info.get("dependencies", [])
        for dep in dependencies:
            dep_type = dep.get("dependency_type")
            dep_project_id = dep.get("project_id")

            # 只处理必需的 Modrinth 内部依赖
            if dep_type == "required" and dep_project_id:
                # 检查是否已经处理过
                if dep_project_id not in self.processed_mods:
                    # 获取依赖项目信息
                    dep_project = await self.api.get_project(dep_project_id)
                    if dep_project:
                        dep_slug = dep_project["slug"]
                        print(f"   发现必需依赖: {dep_slug} (ID: {dep_project_id})")
                        # 递归处理依赖项
                        await self.process_mod(dep_project_id, version)
                    else:
                        print(f"警告: 无法获取必需依赖 '{dep_project_id}' 的详情")
                else:
                    print(f"   依赖 {dep_project_id} 已处理过，跳过")

    async def version_process(self, version: str):
        """
        处理单个版本
        """
        self.version_download_dir = os.path.join(
            self.config["download_dir"], f"{version}-{self.config['mod_loader']}"
        )
        os.makedirs(self.version_download_dir, exist_ok=True)

        # 处理配置中指定的每个模组
        for mod in self.config["mods"]:
            # 支持通过slug或id指定模组
            mod_identifier = mod.get("id") or mod.get("slug")
            if not mod_identifier:
                print(f"模组缺少id或slug，跳过: {mod}")
                continue

            # 如果使用slug，先转换为ID
            project_info = await self.api.get_project(mod_identifier)
            if not project_info:
                print(f"无法找到模组: {mod_identifier}，跳过")
                continue

            mod_id = project_info["id"]  # 使用ID进行内部处理
            mod_slug = project_info["slug"]  # 使用slug用于显示
            print(f"找到模组: {mod_slug} (ID: {mod_id})")

            await self.process_mod(mod_id, version)

    async def download_loop(self):
        for url, filename, download_dir, sha1 in self.download_queue:
            await self.download_file(url, filename, download_dir, sha1)

    def validate_config(self):
        """
        检查配置文件
        """
        if not self.config.get("mc_version"):
            raise ModFetchError("请指定mc_version")
        if not self.config.get("mod_loader"):
            raise ModFetchError("请指定mod_loader")
        if not self.config.get("download_dir"):
            raise ModFetchError("请指定download_dir")
        if not self.config.get("mods"):
            raise ModFetchError("请指定mods")

        if self.config["mod_loader"] not in ["forge", "fabric", "quilt"]:
            raise ModFetchError("mod_loader 只支持 forge, fabric, quilt")
        for mod in self.config["mods"]:
            if not mod.get("slug") and not mod.get("id"):
                raise ModFetchError("请指定 slug 或 id")

    async def start(self):
        self.validate_config()
        for version in self.config["mc_version"]:
            print(f"正在处理版本 {version}")
            await self.version_process(version)
            print(f"处理完成版本 {version}")
        await self.download_loop()
        await self.api.close()
        print("已完成所有任务")
