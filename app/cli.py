"""Flask 命令行工具：初始化表结构、写入演示数据。

用法：
    flask --app run.py init-db
    flask --app run.py seed-db
"""
from datetime import timedelta
from pathlib import Path
from uuid import uuid4

import click
from flask import current_app
from PIL import Image, ImageDraw, ImageFont

from .extensions import db
from .models import Category, Favorite, Item, ItemImage, Message, User
from .seed_data import (
    CATEGORIES,
    DEFAULT_PASSWORD,
    FAVORITES,
    ITEMS,
    MESSAGES,
    USERS,
    seed_time,
)

FONT_CANDIDATES = {
    "regular": [
        r"C:\Windows\Fonts\msyh.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ],
    "bold": [
        r"C:\Windows\Fonts\msyhbd.ttc",
        r"C:\Windows\Fonts\simhei.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ],
}


def _load_font(size: int, bold: bool = False):
    """优先用系统中文字体；找不到时退回 Pillow 默认字体。"""
    for path in FONT_CANDIDATES["bold" if bold else "regular"]:
        if Path(path).exists():
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default()


def _wrap(text: str, per_line: int, max_lines: int = 3) -> list[str]:
    """按固定字数折行，超出部分用省略号。"""
    lines = [text[i : i + per_line] for i in range(0, len(text), per_line)]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1][: per_line - 1] + "…"
    return lines


def _make_placeholder(
    path: Path,
    title: str,
    colors: tuple,
    price: float,
    variant: int,
) -> None:
    """生成一张带渐变、几何装饰和文字的商品占位图（900x675）。"""
    width, height = 900, 675
    image = Image.new("RGB", (width, height))
    draw = ImageDraw.Draw(image)
    start = tuple(int(colors[0][i : i + 2], 16) for i in (1, 3, 5))
    end = tuple(int(colors[1][i : i + 2], 16) for i in (1, 3, 5))

    for y in range(height):
        ratio = y / height
        color = tuple(int(start[i] + (end[i] - start[i]) * ratio) for i in range(3))
        draw.line([(0, y), (width, y)], fill=color)

    overlay = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    deco = ImageDraw.Draw(overlay)
    offset = (variant % 8) * 18
    deco.ellipse((-160 + offset, -220, 200, 140), fill=(255, 255, 255, 26))
    deco.ellipse((width - 300, height - 360, width + 120, height + 60),
                 fill=(255, 255, 255, 18))
    deco.ellipse((width // 2 + 40, 90, width // 2 + 260, 310),
                 fill=(255, 255, 255, 14))
    for i in range(6):
        deco.line(
            [(i * 190 - 100, height), (i * 190 + 240, 0)],
            fill=(255, 255, 255, 10),
            width=22,
        )
    image = Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")
    draw = ImageDraw.Draw(image)

    title_font = _load_font(50, bold=True)
    y = 300
    for line in _wrap(title, 11, 3):
        draw.text((58, y), line, font=title_font, fill=(255, 255, 255))
        y += 72

    price_font = _load_font(46, bold=True)
    draw.text((58, height - 110), f"¥ {price:.0f}", font=price_font,
              fill=(255, 255, 255))
    foot_font = _load_font(24)
    draw.text((width - 300, height - 64), "SK3017 · 校园二手", font=foot_font,
              fill=(255, 255, 255, 200))

    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path, format="JPEG", quality=88, optimize=True)


def _clear_uploads() -> int:
    """清空演示图，避免反复 seed 之后磁盘上堆一堆孤儿文件。"""
    folder = Path(current_app.config["UPLOAD_FOLDER"])
    removed = 0
    if folder.exists():
        for file in folder.glob("*.jpg"):
            file.unlink(missing_ok=True)
            removed += 1
    return removed


def _seed() -> None:
    db.drop_all()
    db.create_all()

    removed = _clear_uploads()
    upload_dir = Path(current_app.config["UPLOAD_FOLDER"])
    category_colors = {row["slug"]: row["colors"] for row in CATEGORIES}

    categories = {}
    for row in CATEGORIES:
        category = Category(
            name=row["name"], slug=row["slug"], icon=row["icon"],
            sort_order=row["sort_order"],
        )
        db.session.add(category)
        categories[row["slug"]] = category
    db.session.flush()

    users = {}
    for row in USERS:
        user = User(
            username=row["username"],
            email=row["email"],
            campus=row["campus"],
            phone=row["phone"],
            bio=row["bio"],
            created_at=seed_time(40),
        )
        user.set_password(DEFAULT_PASSWORD)
        db.session.add(user)
        users[row["username"]] = user
    db.session.flush()

    items = []
    image_index = 0
    for order, (title, description, price, slug, seller_name, condition,
                days_ago, views, status, image_count) in enumerate(ITEMS):
        category = categories[slug]
        item = Item(
            title=title,
            description=description,
            price=price,
            condition=condition,
            campus=users[seller_name].campus,
            status=status,
            views=views,
            seller=users[seller_name],
            category=category,
            created_at=seed_time(days_ago, offset_hours=order % 9),
            updated_at=seed_time(days_ago, offset_hours=order % 9),
        )
        db.session.add(item)
        db.session.flush()
        for image_no in range(image_count):
            image_index += 1
            filename = f"seed_{order + 1:02d}_{image_no + 1}_{uuid4().hex[:8]}.jpg"
            _make_placeholder(
                upload_dir / filename,
                title,
                category_colors[slug],
                float(price),
                variant=image_index,
            )
            db.session.add(
                ItemImage(item_id=item.id, filename=filename, sort_order=image_no)
            )
        items.append(item)
    db.session.flush()

    for username, item_no in FAVORITES:
        db.session.add(Favorite(user_id=users[username].id, item_id=items[item_no - 1].id))

    for username, item_no, content, reply in MESSAGES:
        item = items[item_no - 1]
        created = item.created_at + timedelta(hours=3)
        message = Message(
            item_id=item.id,
            user_id=users[username].id,
            content=content,
            created_at=created,
        )
        db.session.add(message)
        db.session.flush()
        if reply:
            db.session.add(
                Message(
                    item_id=item.id,
                    user_id=item.seller_id,
                    parent_id=message.id,
                    content=reply,
                    created_at=created + timedelta(hours=1),
                )
            )

    db.session.commit()

    click.echo("演示数据写入完成：")
    click.echo(f"  - 分类 {len(CATEGORIES)} 个")
    click.echo(f"  - 用户 {len(USERS)} 个（测试账号 xiaoming / {DEFAULT_PASSWORD}）")
    click.echo(f"  - 商品 {len(ITEMS)} 件，图片 {image_index} 张")
    click.echo(f"  - 收藏 {len(FAVORITES)} 条，留言 {len(MESSAGES)} 组")
    if removed:
        click.echo(f"  - 清理旧演示图 {removed} 张")


def register_cli(app) -> None:
    @app.cli.command("init-db")
    def init_db_command():
        """创建所有表（不会删除已有数据）。"""
        db.create_all()
        click.echo("表结构创建完成。")

    @app.cli.command("seed-db")
    def seed_db_command():
        """重建表结构并写入演示数据（会清空现有数据）。"""
        _seed()

    @app.cli.command("drop-db")
    def drop_db_command():
        """删除所有表，谨慎使用。"""
        db.drop_all()
        click.echo("所有表已删除。")
