"""
mrpack 解析服务

负责从 .mrpack 文件中提取元数据并转换为 ModFetch 配置字典。
"""

import io
import json
import zipfile
from typing import Any, Dict

from loguru import logger


class MrpackResolver:
    """.mrpack 文件解析器"""

    @staticmethod
    async def resolve_to_dict(content_bytes: bytes) -> Dict[str, Any]:
        """
        将 mrpack 字节流解析为配置字典格式

        Args:
            content_bytes: .mrpack 文件的二进制内容

        Returns:
            Dict[str, Any]: 符合 ModFetchConfig.from_dict 预期的字典
        """
        try:
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
                # 读取 modrinth.index.json
                if "modrinth.index.json" not in z.namelist():
                    logger.error("mrpack 文件中缺少 modrinth.index.json")
                    return {}

                index_content = z.read("modrinth.index.json").decode("utf-8")
                index_data = json.loads(index_content)

                # 将 mrpack 索引转换为 ModFetch 配置格式
                config_dict = {
                    "minecraft": {
                        "version": [
                            index_data.get("dependencies", {}).get(
                                "minecraft", "unknown"
                            )
                        ],
                        "mod_loader": index_data.get("dependencies", {}).get(
                            "fabric", None
                        )
                        and "fabric"
                        or index_data.get("dependencies", {}).get("forge", None)
                        and "forge"
                        or index_data.get("dependencies", {}).get("quilt", None)
                        and "quilt"
                        or "fabric",
                        "mods": [],
                        "resourcepacks": [],
                        "shaderpacks": [],
                    },
                    "metadata": {
                        "name": index_data.get("name", "Inherited Pack"),
                        "version": index_data.get("versionId", "1.0.0"),
                        "description": index_data.get("summary", ""),
                    },
                }

                # 处理文件列表
                for file_entry in index_data.get("files", []):
                    path = file_entry.get("path", "")
                    # 尝试从下载链接中恢复 slug 或 ID (如果可能)
                    # 实际上 mrpack 主要是通过文件哈希和 URL 引用的
                    # 在 ModFetch 继承中，我们将其视为额外的 URL 下载或映射回 ModEntry

                    # 简单映射逻辑：将 mods/ 目录下的文件放入 mods 列表
                    if path.startswith("mods/"):
                        # mrpack 的 files 通常只有 URL 和哈希
                        # 我们构造一个简单的条目，Orchestrator 需要能处理这种引用
                        config_dict["minecraft"]["mods"].append(
                            {
                                "id": path.split("/")[-1],  # 临时 ID
                                "extra_data": file_entry,  # 保留原始信息
                            }
                        )
                    elif path.startswith("resourcepacks/"):
                        config_dict["minecraft"]["resourcepacks"].append(
                            path.split("/")[-1]
                        )
                    elif path.startswith("shaderpacks/"):
                        config_dict["minecraft"]["shaderpacks"].append(
                            path.split("/")[-1]
                        )

                logger.info(
                    f"成功从 mrpack 解析了 {len(index_data.get('files', []))} 个文件引用"
                )
                return config_dict

        except Exception as e:
            logger.exception(f"解析 mrpack 失败: {e}")
            return {}
