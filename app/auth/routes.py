"""认证蓝图：注册、登录、退出。"""
import re
from urllib.parse import urlsplit

from flask import Blueprint, flash, g, redirect, render_template, request, session, url_for
from sqlalchemy import func, or_

from ..extensions import db
from ..models import User

bp = Blueprint("auth", __name__, url_prefix="/auth")

USERNAME_RE = re.compile(r"^[A-Za-z0-9_\u4e00-\u9fa5]{2,20}$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[A-Za-z]{2,}$")


def _safe_next(target: str | None) -> str:
    """只允许站内相对路径，防止 ?next=https://evil.com 的开放重定向。"""
    if not target:
        return url_for("market.index")
    parts = urlsplit(target)
    if parts.scheme or parts.netloc:
        return url_for("market.index")
    if not parts.path.startswith("/") or parts.path.startswith("//"):
        return url_for("market.index")
    return target


@bp.route("/register", methods=["GET", "POST"])
def register():
    if g.user:
        return redirect(url_for("market.index"))

    if request.method == "POST":
        username = (request.form.get("username") or "").strip()
        email = (request.form.get("email") or "").strip().lower()
        password = request.form.get("password") or ""
        confirm = request.form.get("confirm") or ""
        campus = (request.form.get("campus") or "").strip()[:64]

        errors = []
        if not USERNAME_RE.match(username):
            errors.append("用户名需为 2~20 位中文、字母、数字或下划线")
        if not EMAIL_RE.match(email) or len(email) > 120:
            errors.append("请输入正确的邮箱地址")
        if len(password) < 6 or len(password) > 32:
            errors.append("密码长度需为 6~32 位")
        if password != confirm:
            errors.append("两次输入的密码不一致")
        if not errors:
            exists = db.session.execute(
                db.select(User).where(or_(User.username == username, User.email == email))
            ).scalars().first()
            if exists:
                errors.append("用户名或邮箱已被注册")

        if errors:
            for message in errors:
                flash(message, "danger")
            return render_template(
                "auth/register.html", form={"username": username, "email": email, "campus": campus}
            ), 400

        user = User(username=username, email=email, campus=campus)
        user.set_password(password)
        db.session.add(user)
        db.session.commit()

        session.clear()
        session["user_id"] = user.id
        flash(f"注册成功，欢迎你，{user.username}！", "success")
        return redirect(url_for("market.index"))

    return render_template("auth/register.html", form={})


@bp.route("/login", methods=["GET", "POST"])
def login():
    if g.user:
        return redirect(url_for("market.index"))

    next_url = request.args.get("next") or request.form.get("next") or ""

    if request.method == "POST":
        account = (request.form.get("account") or "").strip()
        password = request.form.get("password") or ""
        remember = request.form.get("remember") == "on"

        user = db.session.execute(
            db.select(User).where(
                or_(func.lower(User.username) == account.lower(), User.email == account.lower())
            )
        ).scalars().first()

        if user is None or not user.check_password(password):
            # 不区分“用户不存在”和“密码错误”，避免账号枚举
            flash("账号或密码错误，请重试", "danger")
            return render_template("auth/login.html", account=account, next_url=next_url), 401

        session.clear()
        session["user_id"] = user.id
        session.permanent = remember
        flash(f"欢迎回来，{user.username}", "success")
        return redirect(_safe_next(next_url))

    return render_template("auth/login.html", account="", next_url=next_url)


@bp.route("/logout", methods=["POST"])
def logout():
    session.clear()
    flash("你已退出登录", "info")
    return redirect(url_for("market.index"))
