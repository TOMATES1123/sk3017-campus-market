"""商品（校园二手交易）核心蓝图：首页、详情、发布、编辑、收藏、留言。"""
from datetime import date, datetime, time
from decimal import Decimal, InvalidOperation

from flask import (
    Blueprint,
    abort,
    current_app,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError

from ..extensions import db
from ..models import (
    CONDITIONS,
    STATUSES,
    STATUS_OFF_SHELF,
    STATUS_ON_SALE,
    Category,
    Favorite,
    Item,
    ItemImage,
    Message,
)
from ..utils import (
    UploadError,
    escape_like,
    login_required,
    parse_page,
    remove_item_image,
    save_item_image,
)

bp = Blueprint("market", __name__)

SORT_OPTIONS = {
    "new": "最新发布",
    "price_asc": "价格从低到高",
    "price_desc": "价格从高到低",
    "hot": "最多浏览",
}


# ---------------------------------------------------------------------------
# 首页 / 搜索
# ---------------------------------------------------------------------------
@bp.route("/")
def index():
    """商品列表：分类筛选 + 关键词模糊搜索 + 排序 + 分页。"""
    keyword = (request.args.get("q") or "").strip()[:40]
    slug = (request.args.get("category") or "").strip()
    sort = request.args.get("sort", "new")
    if sort not in SORT_OPTIONS:
        sort = "new"
    page = parse_page(request.args.get("page"))

    stmt = db.select(Item).where(Item.status != STATUS_OFF_SHELF)

    active_category = None
    if slug:
        active_category = db.session.execute(
            db.select(Category).where(Category.slug == slug)
        ).scalars().first()
        if active_category is None:
            abort(404)
        stmt = stmt.where(Item.category_id == active_category.id)

    if keyword:
        pattern = f"%{escape_like(keyword)}%"
        stmt = stmt.where(
            or_(
                Item.title.like(pattern, escape="\\"),
                Item.description.like(pattern, escape="\\"),
            )
        )

    order_by = {
        "new": (Item.created_at.desc(), Item.id.desc()),
        "price_asc": (Item.price.asc(), Item.id.desc()),
        "price_desc": (Item.price.desc(), Item.id.desc()),
        "hot": (Item.views.desc(), Item.id.desc()),
    }[sort]
    stmt = stmt.order_by(*order_by)

    pagination = db.paginate(
        stmt,
        page=page,
        per_page=current_app.config["ITEMS_PER_PAGE"],
        error_out=False,
    )

    # 分类导航上的数量用一条 GROUP BY 查出，避免 N+1
    category_rows = db.session.execute(
        db.select(Category, func.count(Item.id))
        .outerjoin(
            Item,
            db.and_(Item.category_id == Category.id, Item.status != STATUS_OFF_SHELF),
        )
        .group_by(Category.id)
        .order_by(Category.sort_order, Category.id)
    ).all()
    category_counts = {category.id: count for category, count in category_rows}
    total_on_sale = db.session.scalar(
        db.select(func.count(Item.id)).where(Item.status == STATUS_ON_SALE)
    )
    today_new = db.session.scalar(
        db.select(func.count(Item.id)).where(
            Item.created_at >= datetime.combine(date.today(), time.min)
        )
    )

    return render_template(
        "market/index.html",
        pagination=pagination,
        keyword=keyword,
        slug=slug,
        sort=sort,
        sort_options=SORT_OPTIONS,
        categories=[row[0] for row in category_rows],
        category_counts=category_counts,
        active_category=active_category,
        total_on_sale=total_on_sale,
        today_new=today_new,
    )


# ---------------------------------------------------------------------------
# 商品详情
# ---------------------------------------------------------------------------
@bp.route("/item/<int:item_id>")
def detail(item_id: int):
    item = db.get_or_404(Item, item_id)
    is_owner = g.user is not None and g.user.id == item.seller_id
    if item.status == STATUS_OFF_SHELF and not is_owner:
        abort(404)

    # 浏览量 +1；用 SQL 自增而不是先读后写，避免并发请求互相覆盖
    db.session.execute(
        db.update(Item).where(Item.id == item.id).values(views=Item.views + 1)
    )
    db.session.commit()
    db.session.refresh(item)

    messages = db.session.execute(
        db.select(Message)
        .where(Message.item_id == item.id, Message.parent_id.is_(None))
        .order_by(Message.created_at.asc())
    ).scalars().all()

    favorited = False
    if g.user:
        favorited = (
            db.session.execute(
                db.select(Favorite.id).where(
                    Favorite.user_id == g.user.id, Favorite.item_id == item.id
                )
            ).scalars().first()
            is not None
        )

    similar = db.session.execute(
        db.select(Item)
        .where(
            Item.category_id == item.category_id,
            Item.id != item.id,
            Item.status == STATUS_ON_SALE,
        )
        .order_by(Item.created_at.desc())
        .limit(4)
    ).scalars().all()

    return render_template(
        "market/detail.html",
        item=item,
        is_owner=is_owner,
        messages=messages,
        favorited=favorited,
        similar=similar,
    )


# ---------------------------------------------------------------------------
# 发布 / 编辑
# ---------------------------------------------------------------------------
def _validate_item_form() -> tuple[dict, list]:
    """校验商品表单，返回 (清洗后的字段, 错误列表)。"""
    title = (request.form.get("title") or "").strip()
    description = (request.form.get("description") or "").strip()
    condition = (request.form.get("condition") or "").strip()
    campus = (request.form.get("campus") or "").strip()[:64]
    price_text = (request.form.get("price") or "").strip()
    category_id = request.form.get("category_id", type=int)

    errors: list = []
    if not 4 <= len(title) <= 80:
        errors.append("商品标题需为 4~80 个字")
    if not 10 <= len(description) <= 1000:
        errors.append("商品描述需为 10~1000 个字")
    if condition not in CONDITIONS:
        errors.append("请选择有效的成色")

    try:
        price = Decimal(price_text).quantize(Decimal("0.01"))
        if price <= 0:
            errors.append("价格必须大于 0")
        elif price > Decimal("99999.99"):
            errors.append("价格不能超过 99999.99 元")
    except (InvalidOperation, ValueError):
        price = Decimal("0")
        errors.append("价格格式不正确，请填写数字")

    category = db.session.get(Category, category_id) if category_id else None
    if category is None:
        errors.append("请选择有效的商品分类")

    return (
        {
            "title": title,
            "description": description,
            "price": price,
            "condition": condition,
            "campus": campus,
            "category": category,
        },
        errors,
    )


def _uploaded_files() -> list:
    return [f for f in request.files.getlist("images") if f and f.filename]


@bp.route("/item/new", methods=["GET", "POST"])
@login_required
def create_item():
    categories = db.session.execute(
        db.select(Category).order_by(Category.sort_order, Category.id)
    ).scalars().all()

    if request.method == "POST":
        fields, errors = _validate_item_form()
        files = _uploaded_files()
        if not 1 <= len(files) <= current_app.config["MAX_IMAGES_PER_ITEM"]:
            errors.append(
                f"请上传 1~{current_app.config['MAX_IMAGES_PER_ITEM']} 张商品图片"
            )

        if not errors:
            item = Item(
                title=fields["title"],
                description=fields["description"],
                price=fields["price"],
                condition=fields["condition"],
                campus=fields["campus"],
                category=fields["category"],
                seller=g.user,
            )
            saved_files: list[str] = []
            try:
                db.session.add(item)
                db.session.flush()  # 先拿到 item.id，再挂图片
                for order, file_storage in enumerate(files):
                    filename = save_item_image(file_storage)
                    saved_files.append(filename)
                    db.session.add(
                        ItemImage(item_id=item.id, filename=filename, sort_order=order)
                    )
                db.session.commit()
            except UploadError as exc:
                db.session.rollback()
                for filename in saved_files:
                    remove_item_image(filename)
                flash(str(exc), "danger")
                return render_template(
                    "market/form.html",
                    item=None,
                    categories=categories,
                    form=request.form,
                    conditions=CONDITIONS,
                ), 400

            flash("发布成功，快去看看吧！", "success")
            return redirect(url_for("market.detail", item_id=item.id))

        for message in errors:
            flash(message, "danger")
        return render_template(
            "market/form.html",
            item=None,
            categories=categories,
            form=request.form,
            conditions=CONDITIONS,
        ), 400

    return render_template(
        "market/form.html",
        item=None,
        categories=categories,
        form={},
        conditions=CONDITIONS,
    )


@bp.route("/item/<int:item_id>/edit", methods=["GET", "POST"])
@login_required
def edit_item(item_id: int):
    item = db.get_or_404(Item, item_id)
    if item.seller_id != g.user.id:
        abort(403)

    categories = db.session.execute(
        db.select(Category).order_by(Category.sort_order, Category.id)
    ).scalars().all()

    if request.method == "POST":
        fields, errors = _validate_item_form()
        keep_ids = {int(i) for i in request.form.getlist("keep_image") if i.isdigit()}
        kept_images = [image for image in item.images if image.id in keep_ids]
        new_files = _uploaded_files()
        total_images = len(kept_images) + len(new_files)
        max_images = current_app.config["MAX_IMAGES_PER_ITEM"]

        if not 1 <= total_images <= max_images:
            errors.append(f"商品需要保留或上传 1~{max_images} 张图片")

        if not errors:
            removed = [image for image in item.images if image.id not in keep_ids]
            removed_filenames = [image.filename for image in removed]
            for image in removed:
                db.session.delete(image)
            db.session.flush()

            item.title = fields["title"]
            item.description = fields["description"]
            item.price = fields["price"]
            item.condition = fields["condition"]
            item.campus = fields["campus"]
            item.category = fields["category"]
            item.updated_at = datetime.now()

            saved_files: list[str] = []
            try:
                for order, file_storage in enumerate(
                    new_files, start=len(kept_images)
                ):
                    filename = save_item_image(file_storage)
                    saved_files.append(filename)
                    db.session.add(
                        ItemImage(item_id=item.id, filename=filename, sort_order=order)
                    )
                db.session.commit()
            except UploadError as exc:
                db.session.rollback()
                for filename in saved_files:
                    remove_item_image(filename)
                flash(str(exc), "danger")
                return redirect(url_for("market.edit_item", item_id=item.id))

            # 数据库提交成功后再删磁盘文件，避免事务回滚后图片找不回来
            for filename in removed_filenames:
                remove_item_image(filename)
            flash("修改已保存", "success")
            return redirect(url_for("market.detail", item_id=item.id))

        for message in errors:
            flash(message, "danger")
        return redirect(url_for("market.edit_item", item_id=item.id))

    return render_template(
        "market/form.html",
        item=item,
        categories=categories,
        form={
            "title": item.title,
            "description": item.description,
            "price": f"{item.price:.2f}",
            "condition": item.condition,
            "campus": item.campus,
            "category_id": item.category_id,
        },
        conditions=CONDITIONS,
    )


@bp.route("/item/<int:item_id>/status", methods=["POST"])
@login_required
def update_status(item_id: int):
    item = db.get_or_404(Item, item_id)
    if item.seller_id != g.user.id:
        abort(403)
    status = request.form.get("status", "")
    if status not in STATUSES:
        abort(400, description="非法的商品状态")
    item.status = status
    db.session.commit()
    flash(f"商品状态已改为「{status}」", "success")
    return redirect(request.referrer or url_for("user.my_items"))


@bp.route("/item/<int:item_id>/delete", methods=["POST"])
@login_required
def delete_item(item_id: int):
    item = db.get_or_404(Item, item_id)
    if item.seller_id != g.user.id:
        abort(403)
    filenames = [image.filename for image in item.images]
    db.session.delete(item)
    db.session.commit()
    for filename in filenames:
        remove_item_image(filename)
    flash("商品已删除", "info")
    return redirect(url_for("user.my_items"))


# ---------------------------------------------------------------------------
# 收藏（Ajax，幂等）
# ---------------------------------------------------------------------------
@bp.route("/item/<int:item_id>/favorite", methods=["POST"])
@login_required
def toggle_favorite(item_id: int):
    item = db.get_or_404(Item, item_id)
    if item.status == STATUS_OFF_SHELF:
        return jsonify(ok=False, msg="该商品已下架，无法收藏"), 400

    existing = db.session.execute(
        db.select(Favorite).where(
            Favorite.user_id == g.user.id, Favorite.item_id == item.id
        )
    ).scalars().first()

    if existing:
        db.session.delete(existing)
        db.session.commit()
        favorited = False
        message = "已取消收藏"
    else:
        db.session.add(Favorite(user_id=g.user.id, item_id=item.id))
        try:
            db.session.commit()
            favorited = True
            message = "收藏成功"
        except IntegrityError:
            # 并发双击时唯一约束会拦住重复插入，这里按“已收藏”处理
            db.session.rollback()
            favorited = True
            message = "该商品已在收藏列表中"

    count = db.session.scalar(
        db.select(func.count(Favorite.id)).where(Favorite.item_id == item.id)
    )
    return jsonify(ok=True, favorited=favorited, count=count, msg=message)


# ---------------------------------------------------------------------------
# 留言与卖家回复
# ---------------------------------------------------------------------------
@bp.route("/item/<int:item_id>/message", methods=["POST"])
@login_required
def post_message(item_id: int):
    item = db.get_or_404(Item, item_id)
    if item.status == STATUS_OFF_SHELF:
        abort(404)

    content = (request.form.get("content") or "").strip()
    if not 2 <= len(content) <= 500:
        flash("留言内容需为 2~500 个字", "danger")
        return redirect(url_for("market.detail", item_id=item.id) + "#messages")
    if item.seller_id == g.user.id:
        flash("不能给自己的商品留言，可以在留言下直接回复买家", "warning")
        return redirect(url_for("market.detail", item_id=item.id) + "#messages")

    db.session.add(Message(item_id=item.id, user_id=g.user.id, content=content))
    db.session.commit()
    flash("留言成功", "success")
    return redirect(url_for("market.detail", item_id=item.id) + "#messages")


@bp.route("/message/<int:message_id>/reply", methods=["POST"])
@login_required
def reply_message(message_id: int):
    parent = db.get_or_404(Message, message_id)
    item = parent.item
    if item.seller_id != g.user.id:
        abort(403)  # 只有卖家能回复自己商品下的留言
    if parent.parent_id is not None:
        abort(400, description="只能回复买家的留言")

    content = (request.form.get("content") or "").strip()
    if not 2 <= len(content) <= 500:
        flash("回复内容需为 2~500 个字", "danger")
    else:
        db.session.add(
            Message(
                item_id=item.id,
                user_id=g.user.id,
                parent_id=parent.id,
                content=content,
            )
        )
        db.session.commit()
        flash("回复成功", "success")
    return redirect(url_for("market.detail", item_id=item.id) + "#messages")
