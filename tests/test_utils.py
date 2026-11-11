"""工具函数单元测试（pytest）。

覆盖 escape_like / parse_page / format_price / time_ago 与图片上传校验，
不依赖数据库。运行：
    pytest tests/test_utils.py -q
"""
import io
import shutil
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from flask import request
from PIL import Image
from werkzeug.datastructures import FileStorage

from app import create_app
from app.utils import (
    UploadError,
    escape_like,
    format_price,
    parse_page,
    save_item_image,
    time_ago,
)

UPLOAD_TMP = Path(__file__).resolve().parent / "_tmp_uploads"


@pytest.fixture()
def app():
    UPLOAD_TMP.mkdir(parents=True, exist_ok=True)
    application = create_app()
    application.config.update(
        TESTING=True,
        UPLOAD_FOLDER=UPLOAD_TMP,
        MAX_IMAGE_BYTES=2 * 1024 * 1024,
    )
    yield application
    shutil.rmtree(UPLOAD_TMP, ignore_errors=True)


def make_image(size=(400, 300), fmt="JPEG", color=(90, 120, 200)) -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def upload(data: bytes, filename: str) -> FileStorage:
    return FileStorage(stream=io.BytesIO(data), filename=filename,
                       content_type="image/jpeg")


def test_escape_like_handles_wildcards():
    assert escape_like("50%") == r"50\%"
    assert escape_like("a_b") == r"a\_b"
    assert escape_like("a\\b") == r"a\\b"
    assert escape_like("普通关键词") == "普通关键词"


def test_parse_page_falls_back_on_invalid_values(app):
    with app.test_request_context("/?page=-3"):
        assert parse_page(request.args.get("page")) == 1
    with app.test_request_context("/?page=abc"):
        assert parse_page(request.args.get("page")) == 1
    with app.test_request_context("/?page=99999"):
        assert parse_page(request.args.get("page")) == 1
    with app.test_request_context("/?page=2"):
        assert parse_page(request.args.get("page")) == 2
    with app.test_request_context("/"):
        assert parse_page(request.args.get("page")) == 1


def test_format_price_keeps_two_decimals():
    assert format_price(12.5) == "12.50"
    assert format_price("9") == "9.00"
    assert format_price(None) == "0.00"


def test_time_ago_reads_naturally():
    now = datetime.now()
    assert time_ago(now - timedelta(seconds=10)) == "刚刚"
    assert time_ago(now - timedelta(minutes=5)) == "5 分钟前"
    assert time_ago(now - timedelta(hours=3)) == "3 小时前"
    assert time_ago(now - timedelta(days=2)) == "2 天前"


def test_save_image_normalizes_to_jpg(app):
    with app.app_context():
        filename = save_item_image(upload(make_image(), "商品图.PNG"))
    assert filename.endswith(".jpg")
    assert (UPLOAD_TMP / filename).exists()


def test_save_image_rejects_wrong_extension(app):
    with app.app_context(), pytest.raises(UploadError, match="格式"):
        save_item_image(upload(b"hello", "note.txt"))


def test_save_image_rejects_fake_image(app):
    with app.app_context(), pytest.raises(UploadError, match="不是有效的图片"):
        save_item_image(upload(b"not really an image", "fake.jpg"))


def test_save_image_rejects_oversized_file(app):
    with app.app_context(), pytest.raises(UploadError, match="2MB"):
        save_item_image(upload(b"0" * (2 * 1024 * 1024 + 10), "big.jpg"))


def test_save_image_rejects_tiny_image(app):
    with app.app_context(), pytest.raises(UploadError, match="太小"):
        save_item_image(upload(make_image(size=(100, 100)), "tiny.jpg"))
