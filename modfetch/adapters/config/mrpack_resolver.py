"""
mrpack 配置来源（自 services.mrpack_resolver 迁移）

负责从 .mrpack 字节流中提取元数据并转换为 ModFetch 配置字典，
供配置继承（from format="mrpack"）使用。
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

        Returns:
            Dict[str, Any]: 符合 ModFetchConfig.from_dict 预期的字典
        """
        try:
            with zipfile.ZipFile(io.BytesIO(content_bytes)) as z:
                if "modrinth.index.json" not in z.namelist():
                    logger.error("mrpack 文件中缺少 modrinth.index.json")
                    return {}

                index_content = z.read("modrinth.index.json").decode("utf-8")
                index_data = json.loads(index_content)

                config_dict: Dict[str, Any] = {
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
                    if path.startswith("mods/"):
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
                    f"成功从 mrpack 解析了 "
                    f"{len(index_data.get('files', []))} 个文件引用"
                )
                return config_dict

        except Exception as e:
            logger.exception(f"解析 mrpack 失败: {e}")
            return {}