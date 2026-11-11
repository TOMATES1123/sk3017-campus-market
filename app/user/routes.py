"""个人中心蓝图：我的商品、我的收藏、收到的留言、资料修改。"""
from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy import func, or_

from ..auth.routes import EMAIL_RE
from ..extensions import db
from ..models import STATUSES, STATUS_ON_SALE, Favorite, Item, Message, User
from ..utils import login_required, parse_page

bp = Blueprint("user", __name__, url_prefix="/me")


def _my_stats(user_id: int) -> dict:
    """个人中心顶部的四个数字，用聚合一次查完。"""
    rows = db.session.execute(
        db.select(Item.status, func.count(Item.id))
        .where(Item.seller_id == user_id)
        .group_by(Item.status)
    ).all()
    by_status = {status: count for status, count in rows}
    return {
        "items_total": sum(by_status.values()),
        "on_sale": by_status.get(STATUS_ON_SALE, 0),
        "sold": by_status.get("已售", 0),
        "favorites": db.session.scalar(
            db.select(func.count(Favorite.id)).where(Favorite.user_id == user_id)
        ),
        "views": db.session.scalar(
            db.select(func.coalesce(func.sum(Item.views), 0)).where(Item.seller_id == user_id)
        ),
    }


@bp.route("/")
@login_required
def center():
    stats = _my_stats(g.user.id)
    recent_items = db.session.execute(
        db.select(Item)
        .where(Item.seller_id == g.user.id)
        .order_by(Item.created_at.desc())
        .limit(4)
    ).scalars().all()
    recent_messages = db.session.execute(
        db.select(Message)
        .join(Item, Message.item_id == Item.id)
        .where(Item.seller_id == g.user.id, Message.user_id != g.user.id)
        .order_by(Message.created_at.desc())
        .limit(5)
    ).scalars().all()
    return render_template(
        "user/center.html",
        stats=stats,
        recent_items=recent_items,
        recent_messages=recent_messages,
    )


@bp.route("/items")
@login_required
def my_items():
    status = request.args.get("status", "")
    if status and status not in STATUSES:
        status = ""
    page = parse_page(request.args.get("page"))

    stmt = db.select(Item).where(Item.seller_id == g.user.id)
    if status:
        stmt = stmt.where(Item.status == status)
    stmt = stmt.order_by(Item.created_at.desc())
    pagination = db.paginate(
        stmt, page=page, per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False
    )
    return render_template(
        "user/items.html",
        pagination=pagination,
        stats=_my_stats(g.user.id),
        status=status,
        statuses=STATUSES,
    )


@bp.route("/favorites")
@login_required
def my_favorites():
    page = parse_page(request.args.get("page"))
    stmt = (
        db.select(Item)
        .join(Favorite, Favorite.item_id == Item.id)
        .where(Favorite.user_id == g.user.id)
        .order_by(Favorite.created_at.desc())
    )
    pagination = db.paginate(
        stmt, page=page, per_page=current_app.config["ITEMS_PER_PAGE"], error_out=False
    )
    return render_template(
        "user/favorites.html", pagination=pagination, stats=_my_stats(g.user.id)
    )


@bp.route("/messages")
@login_required
def my_messages():
    page = parse_page(request.args.get("page"))
    stmt = (
        db.select(Message)
        .join(Item, Message.item_id == Item.id)
        .where(Item.seller_id == g.user.id, Message.user_id != g.user.id)
        .order_by(Message.created_at.desc())
    )
    pagination = db.paginate(
        stmt, page=page, per_page=current_app.config["MESSAGES_PER_PAGE"], error_out=False
    )
    return render_template(
        "user/messages.html", pagination=pagination, stats=_my_stats(g.user.id)
    )


@bp.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    if request.method == "POST":
        email = (request.form.get("email") or "").strip().lower()
        phone = (request.form.get("phone") or "").strip()
        campus = (request.form.get("campus") or "").strip()[:64]
        bio = (request.form.get("bio") or "").strip()[:200]

        errors = []
        if not EMAIL_RE.match(email) or len(email) > 120:
            errors.append("请输入正确的邮箱地址")
        if phone and not (phone.isdigit() and 6 <= len(phone) <= 20):
            errors.append("手机号只能是 6~20 位数字")
        if not errors:
            exists = db.session.execute(
                db.select(User).where(User.email == email, User.id != g.user.id)
            ).scalars().first()
            if exists:
                errors.append("该邮箱已被其他账号使用")

        if errors:
            for message in errors:
                flash(message, "danger")
        else:
            g.user.email = email
            g.user.phone = phone
            g.user.campus = campus
            g.user.bio = bio
            db.session.commit()
            flash("资料已更新", "success")
            return redirect(url_for("user.profile"))

    return render_template("user/profile.html", stats=_my_stats(g.user.id))


@bp.route("/password", methods=["POST"])
@login_required
def change_password():
    current = request.form.get("current_password") or ""
    new = request.form.get("new_password") or ""
    confirm = request.form.get("confirm_password") or ""

    if not g.user.check_password(current):
        flash("当前密码不正确", "danger")
    elif not 6 <= len(new) <= 32:
        flash("新密码长度需为 6~32 位", "danger")
    elif new != confirm:
        flash("两次输入的新密码不一致", "danger")
    elif new == current:
        flash("新密码不能与当前密码相同", "warning")
    else:
        g.user.set_password(new)
        db.session.commit()
        flash("密码修改成功，请牢记新密码", "success")
    return redirect(url_for("user.profile"))


@bp.route("/u/<username>")
def public_profile(username: str):
    """卖家主页：展示联系方式与在售商品。"""
    seller = db.session.execute(
        db.select(User).where(User.username == username)
    ).scalars().first()
    if seller is None:
        abort(404)
    items = db.session.execute(
        db.select(Item)
        .where(Item.seller_id == seller.id, Item.status == STATUS_ON_SALE)
        .order_by(Item.created_at.desc())
        .limit(12)
    ).scalars().all()
    sold_count = db.session.scalar(
        db.select(func.count(Item.id)).where(
            Item.seller_id == seller.id, Item.status == "已售"
        )
    )
    return render_template(
        "user/public_profile.html", seller=seller, items=items, sold_count=sold_count
    )
