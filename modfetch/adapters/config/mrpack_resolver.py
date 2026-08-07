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
    """.mrpack 文件解析器

    从 mrpack（zip）内的 modrinth.index.json 提取元数据与文件列表，
    转换为 ModFetchConfig.from_dict 可消费的配置字典。
    """

    @staticmethod
    async def resolve_to_dict(content_bytes: bytes) -> Dict[str, Any]:
        """
        将 mrpack 字节流解析为配置字典格式

        解析结果：
        - minecraft.version: 索引依赖中的 MC 版本（缺省 "unknown"）
        - minecraft.mod_loader: 按 fabric/forge/quilt 依赖探测加载器
        - minecraft.mods/resourcepacks/shaderpacks: 由 files[].path 前缀分类
        - metadata: 索引的 name/versionId/summary

        解析失败或缺 modrinth.index.json 时返回空 dict（不抛异常，
        由调用方降级回退）。

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

                # 构造 ModFetch 配置骨架
                # 加载器探测链: fabric → forge → quilt，均缺失时回退 fabric
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

                # 处理文件列表: 按 path 前缀分类到 mods/resourcepacks/shaderpacks
                for file_entry in index_data.get("files", []):
                    path = file_entry.get("path", "")
                    if path.startswith("mods/"):
                        # 以文件名作为临时 ID，原始条目存入 extra_data 备用
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
            # 解析异常不向上抛，返回空字典让继承流程降级回退
            logger.exception(f"解析 mrpack 失败: {e}")
            return {}