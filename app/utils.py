"""通用工具：登录校验、CSRF、图片上传校验、分页参数解析等。"""
import io
import secrets
import uuid
from datetime import datetime
from functools import wraps
from pathlib import Path

from flask import abort, current_app, flash, g, jsonify, redirect, request, session, url_for
from PIL import Image, UnidentifiedImageError


# ---------------------------------------------------------------------------
# 登录态
# ---------------------------------------------------------------------------
def login_required(view):
    """未登录时：普通请求跳登录页，Ajax 请求返回 401 JSON。"""

    @wraps(view)
    def wrapped(*args, **kwargs):
        if g.user is None:
            if _wants_json():
                return jsonify(ok=False, msg="登录已过期，请先登录"), 401
            flash("请先登录后再操作", "warning")
            return redirect(url_for("auth.login", next=request.full_path.rstrip("?")))
        return view(*args, **kwargs)

    return wrapped


def _wants_json() -> bool:
    """判断是否 Ajax / JSON 请求。"""
    return (
        request.headers.get("X-Requested-With") == "XMLHttpRequest"
        or request.is_json
        or request.accept_mimetypes.best == "application/json"
    )


# ---------------------------------------------------------------------------
# CSRF：所有写操作都必须带 session 中的随机令牌
# ---------------------------------------------------------------------------
def csrf_token() -> str:
    token = session.get("_csrf_token")
    if not token:
        token = secrets.token_urlsafe(32)
        session["_csrf_token"] = token
    return token


def check_csrf():
    """作为 before_request 钩子使用；失败时 JSON 请求返回 400。"""
    if request.method not in ("POST", "PUT", "PATCH", "DELETE"):
        return None
    token = request.form.get("csrf_token") or request.headers.get("X-CSRF-Token", "")
    expected = session.get("_csrf_token", "")
    if not token or not expected or not secrets.compare_digest(token, expected):
        if _wants_json():
            return jsonify(ok=False, msg="页面已过期，请刷新后重试"), 400
        abort(400, description="表单校验失败（CSRF 令牌不匹配），请刷新页面后重试")
    return None


# ---------------------------------------------------------------------------
# 图片上传
# ---------------------------------------------------------------------------
class UploadError(ValueError):
    """图片校验失败时抛出的业务异常，消息可直接展示给用户。"""


def save_item_image(file_storage) -> str:
    """校验并保存一张商品图，返回新文件名。

    校验链路：扩展名 → 文件大小 → 能否被 Pillow 识别 → 真实格式
    → 最小尺寸。最后统一转 RGB 重存为 jpg，顺带丢掉 EXIF 与恶意载荷。
    """
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    upload_dir.mkdir(parents=True, exist_ok=True)

    raw_name = (file_storage.filename or "").strip()
    if not raw_name:
        raise UploadError("请选择要上传的图片文件")
    ext = raw_name.rsplit(".", 1)[-1].lower() if "." in raw_name else ""
    if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
        raise UploadError("图片格式仅支持 jpg / jpeg / png")

    data = file_storage.read()
    limit = current_app.config["MAX_IMAGE_BYTES"]
    if not data:
        raise UploadError("上传的图片是空文件")
    if len(data) > limit:
        raise UploadError(f"图片不能超过 {limit // 1024 // 1024}MB")

    try:
        probe = Image.open(io.BytesIO(data))
        probe.verify()  # 只校验，不用于读取像素
    except (UnidentifiedImageError, OSError):
        raise UploadError("文件内容不是有效的图片")

    image = Image.open(io.BytesIO(data))
    if image.format not in ("JPEG", "PNG"):
        raise UploadError("图片格式仅支持 jpg / jpeg / png")
    if min(image.size) < 160:
        raise UploadError("图片太小（最短边至少 160 像素），请换一张更清晰的图")

    image = image.convert("RGB")
    image.thumbnail((1280, 1280))
    filename = f"{uuid.uuid4().hex}.jpg"
    image.save(upload_dir / filename, format="JPEG", quality=86, optimize=True)
    return filename


def remove_item_image(filename: str) -> None:
    """删除商品图；文件不存在时静默跳过（图片可能已被手工清理）。"""
    if not filename:
        return
    path = Path(current_app.config["UPLOAD_FOLDER"]) / filename
    try:
        path.unlink(missing_ok=True)
    except OSError as exc:  # pragma: no cover - 基本只可能是权限问题
        current_app.logger.warning("删除图片 %s 失败: %s", path, exc)


# ---------------------------------------------------------------------------
# 查询参数
# ---------------------------------------------------------------------------
def parse_page(raw, default: int = 1, max_page: int = 10000) -> int:
    """把 URL 上的 page 参数转成正整数，非法输入一律回退到第 1 页。

    直接 int() 会把 ?page=abc 变成 500，也可能被塞进超大值拖慢查询。
    """
    try:
        page = int(str(raw))
    except (TypeError, ValueError):
        return default
    if page < 1 or page > max_page:
        return default
    return page


def escape_like(keyword: str) -> str:
    """转义 LIKE 通配符，避免用户输入 % 或 _ 时把整表都匹配出来。"""
    return (
        keyword.replace("\\", "\\\\").replace("%", r"\%").replace("_", r"\_")
    )


def format_price(value) -> str:
    """价格统一显示为两位小数。"""
    try:
        return f"{float(value):.2f}"
    except (TypeError, ValueError):
        return "0.00"


def time_ago(value: datetime) -> str:
    """把时间转成“x 分钟前”这类相对时间，列表页更好读。"""
    if not value:
        return ""
    delta = datetime.now() - value
    seconds = int(delta.total_seconds())
    if seconds < 60:
        return "刚刚"
    if seconds < 3600:
        return f"{seconds // 60} 分钟前"
    if seconds < 86400:
        return f"{seconds // 3600} 小时前"
    if seconds < 86400 * 30:
        return f"{seconds // 86400} 天前"
    return value.strftime("%Y-%m-%d")
