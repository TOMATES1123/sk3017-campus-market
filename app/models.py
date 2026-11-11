"""数据模型：用户、分类、商品、商品图片、收藏、留言。

表关系：
    users 1 ── n items          （发布）
    categories 1 ── n items     （归类）
    items 1 ── n item_images    （1~3 张图）
    users n ── n items          （favorites 中间表，含唯一约束）
    items 1 ── n messages       （留言，parent_id 自关联表示卖家回复）
"""
from datetime import datetime

from werkzeug.security import check_password_hash, generate_password_hash

from .extensions import db

# 商品成色与状态使用常量而不是数据库 ENUM，便于后续扩展
CONDITIONS = ("全新", "九成新", "八成新", "有使用痕迹")
STATUS_ON_SALE = "在售"
STATUS_SOLD = "已售"
STATUS_OFF_SHELF = "下架"
STATUSES = (STATUS_ON_SALE, STATUS_SOLD, STATUS_OFF_SHELF)


class User(db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(32), unique=True, nullable=False, index=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    phone = db.Column(db.String(20), default="")
    campus = db.Column(db.String(64), default="")
    bio = db.Column(db.String(200), default="")
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    items = db.relationship(
        "Item", back_populates="seller", cascade="all, delete-orphan", lazy="dynamic"
    )
    favorites = db.relationship(
        "Favorite", back_populates="user", cascade="all, delete-orphan", lazy="dynamic"
    )

    def set_password(self, raw: str) -> None:
        """只存哈希，永不存明文。"""
        self.password_hash = generate_password_hash(raw)

    def check_password(self, raw: str) -> bool:
        return check_password_hash(self.password_hash, raw)

    @property
    def avatar_text(self) -> str:
        """没有头像上传功能时，用用户名首字作占位头像。"""
        return self.username[:1].upper()

    def __repr__(self) -> str:  # pragma: no cover - 调试用
        return f"<User {self.username}>"


class Category(db.Model):
    __tablename__ = "categories"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(32), unique=True, nullable=False)
    slug = db.Column(db.String(32), unique=True, nullable=False)
    icon = db.Column(db.String(16), default="📦")
    sort_order = db.Column(db.Integer, default=0)

    items = db.relationship("Item", back_populates="category", lazy="dynamic")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Category {self.name}>"


class Item(db.Model):
    __tablename__ = "items"

    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(80), nullable=False)
    description = db.Column(db.Text, nullable=False)
    price = db.Column(db.Numeric(10, 2), nullable=False)
    condition = db.Column(db.String(16), nullable=False, default="九成新")
    campus = db.Column(db.String(64), default="")
    status = db.Column(db.String(8), nullable=False, default=STATUS_ON_SALE, index=True)
    views = db.Column(db.Integer, nullable=False, default=0)

    seller_id = db.Column(db.Integer, db.ForeignKey("users.id"), nullable=False, index=True)
    category_id = db.Column(
        db.Integer, db.ForeignKey("categories.id"), nullable=False, index=True
    )

    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False, index=True)
    updated_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    seller = db.relationship("User", back_populates="items")
    category = db.relationship("Category", back_populates="items")
    images = db.relationship(
        "ItemImage",
        back_populates="item",
        cascade="all, delete-orphan",
        order_by="ItemImage.sort_order",
        lazy="selectin",
    )
    favorites = db.relationship(
        "Favorite", back_populates="item", cascade="all, delete-orphan", lazy="dynamic"
    )
    messages = db.relationship(
        "Message", back_populates="item", cascade="all, delete-orphan", lazy="dynamic"
    )

    @property
    def cover(self) -> str:
        """列表页封面：第一张图，没有图时用占位图。"""
        return self.images[0].filename if self.images else ""

    @property
    def favorite_count(self) -> int:
        return self.favorites.count()

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Item {self.id} {self.title}>"


class ItemImage(db.Model):
    __tablename__ = "item_images"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(
        db.Integer, db.ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename = db.Column(db.String(120), nullable=False)
    sort_order = db.Column(db.Integer, default=0)

    item = db.relationship("Item", back_populates="images")


class Favorite(db.Model):
    __tablename__ = "favorites"
    # 数据库层兜底：同一用户对同一商品只能有一条收藏记录
    __table_args__ = (db.UniqueConstraint("user_id", "item_id", name="uq_favorite_user_item"),)

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    item_id = db.Column(
        db.Integer, db.ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    user = db.relationship("User", back_populates="favorites")
    item = db.relationship("Item", back_populates="favorites")


class Message(db.Model):
    __tablename__ = "messages"

    id = db.Column(db.Integer, primary_key=True)
    item_id = db.Column(
        db.Integer, db.ForeignKey("items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = db.Column(
        db.Integer, db.ForeignKey("users.id", ondelete="CASCADE"), nullable=False
    )
    parent_id = db.Column(
        db.Integer, db.ForeignKey("messages.id", ondelete="CASCADE"), nullable=True
    )
    content = db.Column(db.String(500), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.now, nullable=False)

    item = db.relationship("Item", back_populates="messages")
    author = db.relationship("User")
    replies = db.relationship(
        "Message",
        backref=db.backref("parent", remote_side=[id]),
        cascade="all, delete-orphan",
        order_by="Message.created_at",
    )
