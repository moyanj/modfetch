"""打包适配器

PackagerPort 的 mrpack/zip 实现与按格式分发器：
- MrpackPackager: 生成 Modrinth 标准 .mrpack（download/reference 两种模式）
- ZipPackager: 将目标目录压缩为 .zip 归档
- PackagerDispatcher: 按 OutputSpec.format 路由到具体打包器
"""

from modfetch.adapters.packaging.mrpack import MrpackPackager
from modfetch.adapters.packaging.zip import ZipPackager
from modfetch.adapters.packaging.dispatcher import PackagerDispatcher

__all__ = ["MrpackPackager", "ZipPackager", "PackagerDispatcher"]
