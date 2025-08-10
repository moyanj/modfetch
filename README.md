Project Path: modfetch

Source Tree:

```txt
modfetch
├── README.md
├── config.py
├── core.py
├── downloader.py
├── downloads
│   └── fabric-1.20.1-mods
│       ├── fabric-api-0.92.6+1.20.1.jar
│       ├── iris-1.7.6+mc1.20.1.jar
│       ├── lithium-fabric-mc1.20.1-0.11.3.jar
│       └── sodium-fabric-0.5.13+mc1.20.1.jar
├── extra_urls.py
├── main.py
├── modrinth_api.py
├── mods.toml
└── pyproject.toml

```

`modfetch/config.py`:

```py
import toml
from loguru import logger
import pathlib

DEFAULT_CONFIG_FILE_NAME = "mods.toml"


def load_config(config_path: str) -> dict | None:
    """加载TOML配置文件。"""
    config_file_path = pathlib.Path(config_path)
    logger.info(f"正在加载配置文件: {config_file_path.resolve()}")
    try:
        with open(config_file_path, "r", encoding="utf-8") as f:
            config = toml.load(f)
        return config
    except FileNotFoundError:
        logger.error(
            f"配置文件 '{config_path}' 未找到。请确保配置文件存在或使用 -c 参数指定其路径。"
        )
        return None
    except toml.TomlDecodeError as e:
        logger.error(f"解析 TOML 文件 '{config_path}' 失败: {e}")
        return None
    except Exception as e:
        logger.error(f"加载配置文件 '{config_path}' 时发生未知错误: {e}")
        return None

```

`modfetch/core.py`:

```py
import collections
import pathlib
import requests
from loguru import logger

from modrinth_api import ModrinthAPIClient
from downloader import download_file
from extra_urls import process_extra_mod_urls

DEFAULT_DOWNLOAD_DIR = "./mods"


def process_single_config(
    config_data: dict,
    config_path: str,
    output_dir_override: str | None,
    force_download_all: bool,
) -> dict:
    """处理单个配置文件中的模组下载任务。"""
    logger.info(f"\n======== 开始处理配置文件: {config_path} ========\n")

    mc_version = config_data.get("minecraft_version")
    mod_loader = config_data.get("mod_loader")
    # 命令行参数 `-o` 覆盖配置文件中的 `download_dir`
    download_dir = (
        output_dir_override
        if output_dir_override
        else config_data.get("download_dir", DEFAULT_DOWNLOAD_DIR)
    )

    modrinth_mods_to_process = config_data.get("mods", [])
    extra_mod_urls = config_data.get("extra_mod_urls", [])

    if not mc_version:
        logger.error("配置文件中必须指定 'minecraft_version'。")
        return {
            "status": "error",
            "config_path": config_path,
            "reason": "'minecraft_version' missing",
        }
    if not mod_loader:
        logger.error("配置文件中必须指定 'mod_loader'。")
        return {
            "status": "error",
            "config_path": config_path,
            "reason": "'mod_loader' missing",
        }
    if not modrinth_mods_to_process and not extra_mod_urls:
        logger.warning("配置文件中未指定任何 Modrinth 模组或额外URL。跳过此配置文件。")
        return {
            "status": "skipped",
            "config_path": config_path,
            "reason": "No mods/extra URLs specified",
        }

    try:
        pathlib.Path(download_dir).mkdir(parents=True, exist_ok=True)
        logger.info(f"模组将下载到: {pathlib.Path(download_dir).resolve()}")
    except OSError as e:
        logger.error(f"无法创建下载目录 '{download_dir}': {e}")
        return {
            "status": "error",
            "config_path": config_path,
            "reason": f"Cannot create download directory: {e}",
        }

    client = ModrinthAPIClient()  # Modrinth API 客户端实例
    download_queue = collections.deque(modrinth_mods_to_process)
    processed_project_ids = set()  # 存储已成功处理的项目ID
    modrinth_downloaded_count = 0
    modrinth_skipped_count = 0
    modrinth_failed_count = 0

    logger.info(f"\n--- Modrinth 模组下载开始 ---")
    logger.info(f"Minecraft 版本: {mc_version}, 模组加载器: {mod_loader}\n")

    while download_queue:
        current_mod_entry = download_queue.popleft()
        current_slug = current_mod_entry.get("slug")
        current_version_req = current_mod_entry.get("version")

        if not current_slug:
            logger.warning(
                f"跳过无效的模组条目: {current_mod_entry} (缺少 'slug' 字段)。"
            )
            continue

        logger.info(
            f"\n--- 正在处理 Modrinth 模组: '{current_slug}' (版本: {current_version_req or '最新兼容'}) ---"
        )

        project = client.get_project_by_slug(current_slug)
        if not project:
            logger.error(f"跳过 '{current_slug}'：未能找到其项目详情。")
            modrinth_failed_count += 1
            continue

        project_id = project["id"]
        if project_id in processed_project_ids and not force_download_all:
            logger.info(
                f"跳过 '{current_slug}' (ID: {project_id})：已处理过或已在队列中。"
            )
            modrinth_skipped_count += 1
            continue

        version_data, primary_file = client.get_compatible_versions(
            project_id, mc_version, mod_loader, current_version_req
        )

        if not version_data or not primary_file:
            logger.warning(
                f"跳过 '{current_slug}'：未找到其兼容版本 ({mc_version}, {mod_loader}, 版本: {current_version_req or '最新兼容版本'}) 或主要下载文件。"
            )
            modrinth_failed_count += 1
            continue

        logger.info(
            f"   找到兼容版本: {version_data['version_number']} (发布日期: {version_data.get('date_published', 'N/A')})."
        )

        expected_sha1 = primary_file.get("hashes", {}).get("sha1")
        logger.debug(f"   预期 SHA1: {expected_sha1 or 'N/A'}")

        try:
            download_success = download_file(
                client.session,  # 传递 requests.Session 对象
                primary_file["url"],
                primary_file["filename"],
                download_dir,
                expected_sha1=expected_sha1,
                force_download=force_download_all,  # 强制下载标志传递给下载函数
            )
            if download_success:
                processed_project_ids.add(project_id)
                modrinth_downloaded_count += 1

                for dep in version_data.get("dependencies", []):
                    dep_type = dep.get("dependency_type")
                    dep_project_id = dep.get("project_id")

                    # 只处理必需的 Modrinth 内部依赖
                    if dep_type == "required" and dep_project_id:
                        if dep_project_id not in processed_project_ids:
                            dep_project = client.get_project_by_id(dep_project_id)
                            if dep_project:
                                dep_slug = dep_project["slug"]
                                # 检查是否已经存在于队列中，避免重复添加，并保持其结构为字典
                                if not any(
                                    item.get("slug") == dep_slug
                                    for item in download_queue
                                ):
                                    logger.info(
                                        f"   添加必需依赖 '{dep_slug}' (ID: {dep_project_id}) 到下载队列。"
                                    )
                                    download_queue.append(
                                        {"slug": dep_slug}
                                    )  # 依赖通常下载最新兼容版本
                                else:
                                    logger.debug(
                                        f"   依赖 '{dep_slug}' (ID: {dep_project_id}) 已在队列中。"
                                    )
                            else:
                                logger.warning(
                                    f"警告: 无法获取必需依赖 '{dep_project_id}' 的详情，可能无法下载。"
                                )
                        else:
                            logger.debug(
                                f"   必需依赖 (ID: {dep_project_id}) 已下载或正在处理。"
                            )
                    else:
                        logger.debug(
                            f"   跳过非必需依赖或外部依赖: {dep.get('project_id') or dep.get('file_name')} ({dep_type})"
                        )
            else:
                logger.error(f"由于 '{current_slug}' 下载失败，将跳过其依赖项的处理。")
                modrinth_failed_count += 1

        except Exception as e:
            logger.error(f"处理 '{current_slug}' 时发生未捕获的错误: {e}")
            modrinth_failed_count += 1

    logger.info("\n--- Modrinth 模组下载完成 ---")
    logger.info(f"共处理 {len(processed_project_ids)} 个 Modrinth 模组。")

    # 处理额外模组URL
    extra_url_success, extra_url_failed = process_extra_mod_urls(
        extra_mod_urls,
        mc_version,
        mod_loader,
        download_dir,
        client.session,
        force_download_all,
    )

    logger.info(f"\n======== 配置文件 '{config_path}' 处理完毕 ========")
    logger.info(f"下载目录: {pathlib.Path(download_dir).resolve()}")
    logger.info(f"Modrinth 模组下载成功: {modrinth_downloaded_count}")
    logger.info(f"Modrinth 模组跳过 (已存在/已处理): {modrinth_skipped_count}")
    logger.info(f"Modrinth 模组下载失败: {modrinth_failed_count}")
    logger.info(f"额外URL模组下载成功: {extra_url_success}")
    logger.info(f"额外URL模组下载失败: {extra_url_failed}")
    logger.info("--------------------------------\n")

    return {
        "config_path": config_path,
        "status": (
            "completed"
            if modrinth_failed_count == 0 and extra_url_failed == 0
            else "completed_with_errors"
        ),
        "modrinth_downloaded": modrinth_downloaded_count,
        "modrinth_skipped": modrinth_skipped_count,
        "modrinth_failed": modrinth_failed_count,
        "extra_url_downloaded": extra_url_success,
        "extra_url_failed": extra_url_failed,
    }

```

`modfetch/downloader.py`:

```py
import os
import pathlib
import hashlib
import sys
from loguru import logger
from tqdm import tqdm
import requests
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
)
from typing import Optional


def calculate_file_sha1(filepath: pathlib.Path) -> str | None:
    """计算文件的 SHA1 哈希值。"""
    sha1 = hashlib.sha1()
    try:
        with open(filepath, "rb") as f:
            while True:
                chunk = f.read(8192)
                if not chunk:
                    break
                sha1.update(chunk)
        return sha1.hexdigest()
    except OSError as e:
        logger.error(f"计算文件 '{filepath}' 的 SHA1 时发生文件系统错误: {e}")
        return None
    except Exception as e:
        logger.error(f"计算文件 '{filepath}' 的 SHA1 时发生未知错误: {e}")
        return None


@retry(
    wait=wait_exponential(multiplier=1, min=2, max=10),
    stop=stop_after_attempt(5),
    retry=retry_if_exception_type(requests.exceptions.RequestException),
)
def download_file(
    session: requests.Session,
    url: str,
    filename: str,
    download_dir: str,
    expected_sha1: Optional[str] = None,
    force_download: bool = False,
) -> bool:
    """
    下载文件到指定目录，支持重试和进度条，并进行SHA1校验。
    如果 force_download 为 True，则忽略文件存在和SHA1校验，直接重新下载。
    """
    file_path = pathlib.Path(download_dir) / filename
    logger.info(f"-> 正在下载 {filename} 到 {file_path}...")

    if file_path.exists() and not force_download:
        current_size = file_path.stat().st_size
        if current_size > 0:
            if expected_sha1:
                logger.info(f"   文件 {filename} 已存在，正在校验哈希...")
                actual_sha1 = calculate_file_sha1(file_path)
                if actual_sha1 == expected_sha1:
                    logger.info(f"   文件 {filename} 哈希校验成功，跳过下载。")
                    return True
                else:
                    logger.warning(
                        f"   文件 {filename} 哈希不匹配！期望: {expected_sha1[:10]}..., 实际: {actual_sha1[:10]}.... 将重新下载。"  # type: ignore
                    )
            else:
                logger.info(
                    f"   文件 {filename} 已存在且大小非零，跳过下载（无预期哈希进行校验）。"
                )
                return True
        else:
            logger.warning(f"   文件 {filename} 已存在但大小为零，将重新下载。")

    try:
        with session.get(url, stream=True, timeout=30) as r:
            r.raise_for_status()  # 如果响应状态码不是200，则抛出HTTPError
            total_size = int(r.headers.get("content-length", 0))
            with open(file_path, "wb") as f:
                # tqdm 的 `disable` 参数在测试等场景可能有用
                with tqdm(
                    total=total_size,
                    unit="B",
                    unit_scale=True,
                    desc=filename,
                    ncols=80,
                    file=sys.stdout,
                ) as pbar:
                    for chunk in r.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            pbar.update(len(chunk))

        if expected_sha1:
            actual_sha1 = calculate_file_sha1(file_path)
            if actual_sha1 == expected_sha1:
                logger.info(f"✅ {filename} 下载成功并哈希校验通过。")
                return True
            else:
                logger.error(
                    f"❌ {filename} 下载成功但哈希校验失败！期望: {expected_sha1[:10]}..., 实际: {actual_sha1[:10]}.... 尝试删除并重新下载。"  # type: ignore
                )
                if file_path.exists():
                    os.remove(file_path)
                # 重新抛出异常以触发 tenacity 重试
                raise requests.exceptions.RequestException(
                    f"SHA1 mismatch for {filename}"
                )
        else:
            logger.info(f"✅ {filename} 下载成功。")
            return True

    except requests.exceptions.RequestException as e:
        logger.error(f"❌ 下载 {filename} 失败 ({url}): {e}")
        if file_path.exists():
            os.remove(file_path)
        raise  # 重新抛出异常，让 tenacity 捕获并重试
    except Exception as e:
        logger.error(f"❌ 下载 {filename} 时发生未知错误: {e}")
        if file_path.exists():
            os.remove(file_path)
        raise  # 重新抛出异常

```

`modfetch/extra_urls.py`:

```py
import urllib.parse
import os
from loguru import logger
import requests
from downloader import download_file  # 从downloader模块导入下载函数


def process_extra_mod_urls(
    urls: list[str],
    mc_version: str,
    mod_loader: str,
    download_dir: str,
    session: requests.Session,
    force_download: bool,
) -> tuple[int, int]:
    """
    处理并下载额外的模组URL，支持占位符替换和自动提取文件名。
    返回 (成功下载数, 失败下载数)
    """
    logger.info(f"\n--- 正在处理额外模组URL ---")
    if not urls:
        logger.info("未在配置中指定额外模组URL。")
        return 0, 0

    success_count = 0
    fail_count = 0

    for url_template in urls:
        try:
            # 替换 URL 中的占位符
            formatted_url = url_template.format(
                mc_version=mc_version, mod_loader=mod_loader
            )
        except KeyError as e:
            logger.warning(
                f"警告: URL '{url_template}' 包含无法解析的占位符: {e}。跳过此URL。"
            )
            fail_count += 1
            continue
        except Exception as e:
            logger.warning(
                f"警告: 处理URL '{url_template}' 时发生未知错误: {e}。跳过此URL。"
            )
            fail_count += 1
            continue

        # 从格式化后的URL中提取文件名
        parsed_url = urllib.parse.urlparse(formatted_url)
        filename = os.path.basename(parsed_url.path)

        if not filename or filename == "/":  # handle cases like "example.com/"
            logger.warning(
                f"警告: 无法从URL '{formatted_url}' 提取有效文件名。跳过此URL。"
            )
            fail_count += 1
            continue

        # 确保文件名是合法的，有时URL末尾会有查询参数或片段标识符，需要进一步清理
        if "?" in filename:
            filename = filename.split("?")[0]
        if "#" in filename:
            filename = filename.split("#")[0]

        logger.info(f"尝试下载额外模组: {formatted_url}")
        try:
            # 外部URL通常没有提供哈希值，下载时如果 force_download 为 True，expected_sha1 也传 None
            if download_file(
                session,
                formatted_url,
                filename,
                download_dir,
                expected_sha1=None,
                force_download=force_download,
            ):
                success_count += 1
            else:
                # download_file 已经处理了日志和重试，如果返回 False 则表示最终失败
                fail_count += 1
        except Exception as e:
            logger.error(f"下载外部模组 '{filename}' 最终失败: {e}")
            fail_count += 1
    logger.info("--- 额外模组URL处理完成 ---")
    return success_count, fail_count

```

`modfetch/main.py`:

```py
import argparse
import sys
from loguru import logger
import sys

# 从 src 包导入模块
from config import load_config, DEFAULT_CONFIG_FILE_NAME
from core import process_single_config


def parse_arguments():
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="一个自动根据MC版本、模组加载器和模组列表从Modrinth下载模组（及依赖）的程序，支持额外URL和TOML配置。可以处理多个配置文件。",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument(
        "-c",
        "--config",
        type=str,
        nargs="+",  # 允许一个或多个配置文件
        default=[DEFAULT_CONFIG_FILE_NAME],
        help="指定一个或多个 TOML 配置文件的路径。例如: -c config1.toml config2.toml",
    )
    parser.add_argument(
        "-o",
        "--output",
        type=str,
        default=None,
        help="指定模组的通用下载目录。此参数会覆盖所有配置文件中的 download_dir。",
    )
    parser.add_argument(
        "-f",
        "--force-download",
        action="store_true",
        help="强制重新下载所有文件，即使它们已存在且哈希匹配。",
    )
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="启用详细输出 (DEBUG 级别日志)。"
    )

    args = parser.parse_args()
    return args


def main():
    """程序主入口点，处理所有指定的配置文件。"""
    args = parse_arguments()

    # 配置 loguru 日志级别
    logger.remove()  # 移除默认的 stderr handler
    if args.verbose:
        level = "DEBUG"  # 详细模式
    else:
        level = "INFO"  # 默认模式

    logger.add(sys.stdout, level=level, format="{elapsed} - {message}")

    logger.info("程序启动。")
    if args.verbose:
        logger.debug("详细输出模式已启用。")

    all_results = []
    # 遍历所有配置路径
    for config_file_path in args.config:
        config_data = load_config(config_file_path)
        if config_data:
            result = process_single_config(
                config_data, config_file_path, args.output, args.force_download
            )
            all_results.append(result)
        else:
            logger.error(f"无法加载配置文件 '{config_file_path}'，跳过处理。")
            all_results.append(
                {
                    "config_path": config_file_path,
                    "status": "config_load_failed",
                    "modrinth_downloaded": 0,
                    "modrinth_skipped": 0,
                    "modrinth_failed": 0,
                    "extra_url_downloaded": 0,
                    "extra_url_failed": 0,
                }
            )

    logger.info("\n--- 所有任务概览 ---")
    total_modrinth_downloaded = 0
    total_modrinth_skipped = 0
    total_modrinth_failed = 0
    total_extra_url_downloaded = 0
    total_extra_url_failed = 0

    for res in all_results:
        summary_line = f"配置文件: {res.get('config_path', 'N/A')}"
        status = res.get("status", "未知")

        if status == "completed":
            summary_line += f" - 状态: 成功完成"
        elif status == "completed_with_errors":
            summary_line += f" - 状态: 完成但有错误"
        elif status == "error":
            summary_line += f" - 状态: 处理错误 ({res.get('reason', '未知')})"
        elif status == "skipped":
            summary_line += f" - 状态: 跳过 ({res.get('reason', '未知')})"
        elif status == "config_load_failed":
            summary_line += f" - 状态: 配置加载失败"
        else:
            summary_line += f" - 状态: {status}"

        logger.info(summary_line)
        if status in ["completed", "completed_with_errors"]:
            logger.info(
                f"  Modrinth (下载/跳过/失败): {res.get('modrinth_downloaded', 0)}/{res.get('modrinth_skipped', 0)}/{res.get('modrinth_failed', 0)}"
            )
            logger.info(
                f"  额外URL (下载/失败): {res.get('extra_url_downloaded', 0)}/{res.get('extra_url_failed', 0)}"
            )
            total_modrinth_downloaded += res.get("modrinth_downloaded", 0)
            total_modrinth_skipped += res.get("modrinth_skipped", 0)
            total_modrinth_failed += res.get("modrinth_failed", 0)
            total_extra_url_downloaded += res.get("extra_url_downloaded", 0)
            total_extra_url_failed += res.get("extra_url_failed", 0)
        elif status in ["error", "skipped", "config_load_failed"]:
            logger.info(f"  详细信息请查看上方日志。")

    logger.info("\n--- 总计统计 ---")
    logger.info(f"总 Modrinth 模组下载成功: {total_modrinth_downloaded}")
    logger.info(f"总 Modrinth 模组跳过 (已存在/已处理): {total_modrinth_skipped}")
    logger.info(f"总 Modrinth 模组下载失败: {total_modrinth_failed}")
    logger.info(f"总 额外URL模组下载成功: {total_extra_url_downloaded}")
    logger.info(f"总 额外URL模组下载失败: {total_extra_url_failed}")
    logger.info("\n所有任务完成。")
    logger.info("--------------------------------")


if __name__ == "__main__":
    main()

```

`modfetch/modrinth_api.py`:

```py
import requests
from loguru import logger
from tenacity import (
    retry,
    wait_exponential,
    stop_after_attempt,
    retry_if_exception_type,
)
import functools
from typing import Optional

MODRINTH_API_BASE_URL = "https://api.modrinth.com/v2"


class ModrinthAPIClient:
    """Modrinth API 交互客户端。"""

    def __init__(self):
        self.session = requests.Session()
        self._project_id_to_slug_cache = (
            {}
        )  # 简单的内存缓存，用于 Project ID 到 Slug 的映射

    @retry(
        wait=wait_exponential(multiplier=1, min=2, max=10),
        stop=stop_after_attempt(5),
        retry=retry_if_exception_type(requests.exceptions.RequestException),
    )
    def _make_request(
        self, endpoint: str, params: Optional[dict] = None
    ) -> dict | None:
        """发送HTTP GET请求到Modrinth API，支持重试。"""
        url = f"{MODRINTH_API_BASE_URL}/{endpoint}"
        logger.debug(f"Making API request to: {url} with params: {params}")
        response = self.session.get(url, params=params, timeout=10)
        response.raise_for_status()  # 如果响应状态码不是200，则抛出HTTPError
        return response.json()

    # 使用 LRU Cache 缓存 API 响应可以减少重复请求
    @functools.lru_cache(maxsize=128)
    def get_project_by_slug(self, slug: str) -> dict | None:
        """通过slug获取模组项目详情。"""
        logger.info(f"-> 正在查询模组项目详情 (slug: {slug})...")
        try:
            data = self._make_request(f"project/{slug}")
            if data and "id" in data and "slug" in data:
                self._project_id_to_slug_cache[data["id"]] = data["slug"]
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Modrinth API 请求失败 (slug: {slug}): {e}")
            return None

    @functools.lru_cache(maxsize=128)
    def get_project_by_id(self, project_id: str) -> dict | None:
        """通过项目ID获取模组项目详情。"""
        logger.info(f"-> 正在查询模组项目详情 (ID: {project_id})...")
        try:
            data = self._make_request(f"project/{project_id}")
            if data and "id" in data and "slug" in data:
                self._project_id_to_slug_cache[data["id"]] = data["slug"]
            return data
        except requests.exceptions.RequestException as e:
            logger.error(f"Modrinth API 请求失败 (ID: {project_id}): {e}")
            return None

    def get_compatible_versions(
        self,
        project_id: str,
        mc_version: str,
        mod_loader: str,
        specific_version: Optional[str] = None,
    ) -> tuple[dict | None, dict | None]:
        """
        获取与指定Minecraft版本/模组加载器兼容的模组版本。
        如果指定 specific_version，则尝试查找该精确版本。
        返回 (version_data, primary_file_data)
        """
        logger.info(
            f"-> 正在查找兼容版本 (项目ID: {project_id}, MC: {mc_version}, 加载器: {mod_loader}, 指定版本: {specific_version or '最新'})..."
        )

        params = {"game_versions": f'["{mc_version}"]', "loaders": f'["{mod_loader}"]'}
        try:
            all_compatible_versions = self._make_request(
                f"project/{project_id}/version", params=params
            )
        except requests.exceptions.RequestException as e:
            logger.error(f"获取 {project_id} 的兼容版本时 API 请求失败: {e}")
            return None, None

        if not all_compatible_versions:
            logger.warning(f"   未找到与 {mc_version} / {mod_loader} 兼容的任何版本。")
            return None, None

        target_version_data = None

        if specific_version:
            target_version_data = next(
                (
                    v
                    for v in all_compatible_versions
                    if v.get("version_number") == specific_version
                ),
                None,
            )
            if not target_version_data:
                logger.warning(
                    f"   未找到指定版本 '{specific_version}' 与 {mc_version}/{mod_loader} 兼容。"
                )
                return None, None
            logger.info(f"   已找到指定版本 '{specific_version}'。")
        else:
            all_compatible_versions.sort(  # type: ignore
                key=lambda x: x.get("date_published", ""), reverse=True
            )
            target_version_data = next((v for v in all_compatible_versions), None)
            if not target_version_data:
                logger.warning(f"   未找到任何最新兼容版本。")
                return None, None
            logger.info(
                f"   已找到最新兼容版本 '{target_version_data.get('version_number')}'。"
            )

        primary_file = next(
            (f for f in target_version_data.get("files", []) if f.get("primary")), None
        )
        if primary_file:
            return target_version_data, primary_file
        else:
            logger.warning(
                f"   找到版本 '{target_version_data.get('version_number')}' 但未找到主要下载文件。"
            )
            return None, None

```

`modfetch/mods.toml`:

```toml
# Minecraft 版本，例如 "1.20.1"
minecraft_version = "1.20.1"

# 模组加载器，可选值: "fabric", "forge", "quilt" 等
mod_loader = "fabric"

# 模组下载目录，程序将在此目录下创建 'mods' 文件夹
download_dir = "./downloads/fabric-1.20.1-mods" # 这是该配置文件的特定下载目录

# Modrinth 模组列表。
# 每个模组用一个表格表示，包含 'slug'。
# 'version' 是可选的，如果指定，将下载该精确版本；
# 否则，将下载最新兼容版本。
[[mods]]
slug = "sodium"

[[mods]]
slug = "iris"
# 没有指定版本，将下载最新兼容的 Iris

[[mods]]
slug = "lithium"

[[mods]]
slug = "fabric-api"

extra_mod_urls = [
    # "https://media.forgecdn.net/files/4709/200/roughlyenoughitems-1.20.1-13.0.603.jar",
    # "https://your.custom.repo.com/some_utility_mod_{mc_version}_for_{mod_loader}.jar"
]

```

`modfetch/pyproject.toml`:

```toml
[project]
name = "modfetch"
version = "0.1.0"
description = "Add your description here"
readme = "README.md"
requires-python = ">=3.13"
dependencies = [
    "loguru>=0.7.3",
    "requests>=2.32.4",
    "tenacity>=9.1.2",
    "toml>=0.10.2",
    "tqdm>=4.67.1",
]

```