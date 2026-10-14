"""私有存储文件登记表：哪些表引用了存储文件，应用会生成哪些存储键。

孤儿文件回收（app/services/file_retention.py）和备份脚本（scripts/backup_restore.py）共用这份登记表。
新增写入私有存储的功能时，引用表和键格式都要在这里登记：
- 漏登记引用表：孤儿回收会把仍在使用的文件当成孤儿删掉，备份也不会带上它；
- 漏登记键格式：孤儿回收不会处理这类文件，只是少回收，不会误删。
本模块只依赖标准库，备份脚本可以直接导入。
"""

import re
from typing import NamedTuple


class FileReference(NamedTuple):
    table: str
    storage_column: str  # 存储后端名；空串与 "local" 都表示本地磁盘
    key_column: str  # 存储键；空串表示这一行没有文件


REFERENCES = (
    FileReference("paper_assets", "storage", "storage_key"),
    FileReference("image_assets", "storage", "storage_key"),
    FileReference("site_banners", "image_storage", "image_key"),
)

# 应用生成的存储键格式。存储目录里的其他文件（运维放进来的密钥、备份、日志等）一律不参与孤儿回收。
MANAGED_KEY = re.compile(
    r"[0-9a-f]{32}/[0-9a-f]{32}/(?:paper\.pdf|thumbnail(?:-\d+)?\.jpg|page-\d+\.jpg)"  # 归档及每页缩略图
    r"|imports/[0-9a-f]{24}/[0-9A-Za-z_-]+"  # 演示资料导入（scripts/import_demo_catalog.py）
    r"|images/\d+/[0-9a-f]{32}\.png"  # 生图结果（image_assets）
    r"|site/banners/[0-9a-f]{32}\.(?:jpg|png|webp)"  # 首页 Banner（site_content）
)
