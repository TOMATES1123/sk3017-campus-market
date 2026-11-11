"""数据统计蓝图：扩展功能，用 ECharts 展示平台运营数据。

所有聚合都在 MySQL 里完成（GROUP BY / COUNT），前端只负责渲染。
"""
from datetime import date, datetime, timedelta

from flask import Blueprint, jsonify, render_template, request
from sqlalchemy import func

from ..extensions import db
from ..models import Category, Favorite, Item, Message, User
from ..utils import parse_page

bp = Blueprint("stats", __name__, url_prefix="/stats")

PRICE_BUCKETS = (
    ("50 元以下", 0, 50),
    ("50~100 元", 50, 100),
    ("100~300 元", 100, 300),
    ("300~500 元", 300, 500),
    ("500~1000 元", 500, 1000),
    ("1000 元以上", 1000, None),
)


def _range_days() -> int:
    """趋势图时间范围，只允许 7 / 14 / 30 天，防止构造超大查询。"""
    days = request.args.get("days", type=int, default=14)
    return days if days in (7, 14, 30) else 14


@bp.route("/")
def dashboard():
    total_items = db.session.scalar(db.select(func.count(Item.id))) or 0
    on_sale = db.session.scalar(
        db.select(func.count(Item.id)).where(Item.status == "在售")
    ) or 0
    sold = db.session.scalar(
        db.select(func.count(Item.id)).where(Item.status == "已售")
    ) or 0
    total_users = db.session.scalar(db.select(func.count(User.id))) or 0
    total_views = db.session.scalar(db.select(func.coalesce(func.sum(Item.views), 0))) or 0
    total_messages = db.session.scalar(db.select(func.count(Message.id))) or 0
    total_favorites = db.session.scalar(db.select(func.count(Favorite.id))) or 0
    sold_amount = db.session.scalar(
        db.select(func.coalesce(func.sum(Item.price), 0)).where(Item.status == "已售")
    ) or 0
    avg_price = db.session.scalar(db.select(func.coalesce(func.avg(Item.price), 0))) or 0
    favorite_rate = round(total_favorites / total_items * 100, 1) if total_items else 0

    hot_items = db.session.execute(
        db.select(Item).order_by(Item.views.desc(), Item.id.desc()).limit(5)
    ).scalars().all()

    return render_template(
        "stats/dashboard.html",
        kpi={
            "total_items": total_items,
            "on_sale": on_sale,
            "sold": sold,
            "users": total_users,
            "views": total_views,
            "messages": total_messages,
            "favorites": total_favorites,
            "sold_amount": float(sold_amount),
            "avg_price": float(avg_price),
            "favorite_rate": favorite_rate,
        },
        hot_items=hot_items,
        days=_range_days(),
    )


@bp.route("/api/category")
def api_category():
    """各分类商品数量与平均价格（饼图 + 提示框）。"""
    rows = db.session.execute(
        db.select(
            Category.name,
            func.count(Item.id).label("total"),
            func.coalesce(func.avg(Item.price), 0).label("avg_price"),
        )
        .outerjoin(Item, Item.category_id == Category.id)
        .group_by(Category.id)
        .order_by(func.count(Item.id).desc())
    ).all()

    return jsonify(
        ok=True,
        data=[
            {
                "name": name,
                "value": int(total),
                "avg_price": round(float(avg_price), 2),
            }
            for name, total, avg_price in rows
        ],
    )


@bp.route("/api/trend")
def api_trend():
    """最近 N 天每天的新增商品数（折线图），没有数据的日期补 0。"""
    days = _range_days()
    start = date.today() - timedelta(days=days - 1)

    rows = db.session.execute(
        db.select(func.date(Item.created_at), func.count(Item.id))
        .where(Item.created_at >= datetime.combine(start, datetime.min.time()))
        .group_by(func.date(Item.created_at))
    ).all()
    counts = {str(day): int(count) for day, count in rows}

    labels, values = [], []
    for offset in range(days):
        day = start + timedelta(days=offset)
        labels.append(day.strftime("%m-%d"))
        values.append(counts.get(str(day), 0))

    return jsonify(ok=True, labels=labels, values=values, days=days)


@bp.route("/api/price")
def api_price():
    """价格区间分布（柱状图），用条件聚合一次查完。"""
    total_expr = func.count(Item.id).label("total")
    columns = []
    for label, low, high in PRICE_BUCKETS:
        condition = Item.price >= low
        if high is not None:
            condition = db.and_(condition, Item.price < high)
        columns.append(func.sum(db.case((condition, 1), else_=0)).label(label))

    row = db.session.execute(db.select(*columns, total_expr)).one()
    labels = [bucket[0] for bucket in PRICE_BUCKETS]
    values = [int(value or 0) for value in row[: len(PRICE_BUCKETS)]]

    return jsonify(ok=True, labels=labels, values=values, total=int(row[-1] or 0))


@bp.route("/api/status")
def api_status():
    """商品状态构成（环形图）。"""
    rows = db.session.execute(
        db.select(Item.status, func.count(Item.id)).group_by(Item.status)
    ).all()
    return jsonify(
        ok=True,
        data=[{"name": status, "value": int(count)} for status, count in rows],
    )
