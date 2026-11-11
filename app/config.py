"""项目配置。

数据库连接信息全部来自环境变量（可用项目根目录的 .env 文件提供），
避免把账号密码硬编码进代码后提交到仓库。
"""
import os
from pathlib import Path

from dotenv import load_dotenv

# app/config.py → app → 项目根目录
BASE_DIR = Path(__file__).resolve().parent.parent
load_dotenv(BASE_DIR / ".env")


def _database_uri() -> str:
    """优先使用 DATABASE_URL；否则用分项配置拼出 MySQL 连接串。"""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    user = os.environ.get("DB_USER", "root")
    password = os.environ.get("DB_PASSWORD", "")
    host = os.environ.get("DB_HOST", "127.0.0.1")
    port = os.environ.get("DB_PORT", "3306")
    name = os.environ.get("DB_NAME", "sk3017_market")
    return (
        f"mysql+pymysql://{user}:{password}@{host}:{port}/{name}?charset=utf8mb4"
    )


class Config:
    """基础配置。"""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-only-secret-change-me")

    SQLALCHEMY_DATABASE_URI = _database_uri()
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    # 连接池保活，避免 MySQL 8 小时断连后第一次请求报 Lost connection
    SQLALCHEMY_ENGINE_OPTIONS = {"pool_pre_ping": True, "pool_recycle": 280}

    # 单次请求体上限（用于拦截超大上传），真正的图片大小在业务层校验
    MAX_CONTENT_LENGTH = 12 * 1024 * 1024
    UPLOAD_FOLDER = BASE_DIR / "app" / "static" / "uploads" / "items"
    ALLOWED_EXTENSIONS = {"jpg", "jpeg", "png"}
    MAX_IMAGE_BYTES = 2 * 1024 * 1024
    MAX_IMAGES_PER_ITEM = 3

    ITEMS_PER_PAGE = 9
    MESSAGES_PER_PAGE = 20

    # 中文站点的 JSON 不转义，方便调试与阅读
    JSON_AS_ASCII = False
