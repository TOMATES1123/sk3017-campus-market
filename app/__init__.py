"""应用工厂。

职责：加载配置 → 初始化扩展 → 注册蓝图 → 注册请求钩子 / 错误处理 / 模板过滤器。
"""
import mimetypes
import os

from flask import Flask, g, jsonify, render_template, request, session, url_for

from .config import Config
from .extensions import db
from .utils import check_csrf, csrf_token, format_price, time_ago

# Windows 注册表有时把 .js 识别成 text/plain，浏览器在 nosniff 下会拒绝执行
mimetypes.add_type("application/javascript", ".js")
mimetypes.add_type("text/css", ".css")


def create_app(config_object=Config) -> Flask:
    app = Flask(__name__)
    app.config.from_object(config_object)

    db.init_app(app)
    os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)

    _register_blueprints(app)
    _register_request_hooks(app)
    _register_template_helpers(app)
    _register_error_handlers(app)

    from .cli import register_cli

    register_cli(app)
    return app


def _register_blueprints(app: Flask) -> None:
    from .auth.routes import bp as auth_bp
    from .market.routes import bp as market_bp
    from .stats.routes import bp as stats_bp
    from .user.routes import bp as user_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(market_bp)
    app.register_blueprint(stats_bp)
    app.register_blueprint(user_bp)


def _register_request_hooks(app: Flask) -> None:
    from .models import Category, User

    @app.before_request
    def load_logged_in_user():
        """每个请求只查一次用户，挂在 g 上供视图与模板使用。"""
        user_id = session.get("user_id")
        g.user = db.session.get(User, user_id) if user_id else None
        if user_id and g.user is None:
            # 用户被删除但 session 还留着，清掉避免反复查询
            session.clear()

    @app.before_request
    def protect_from_csrf():
        return check_csrf()

    @app.context_processor
    def inject_globals():
        """全站模板都能拿到当前用户、导航分类和 CSRF 令牌。"""
        categories = db.session.execute(
            db.select(Category).order_by(Category.sort_order, Category.id)
        ).scalars().all()

        def page_url(target_page: int) -> str:
            """保留当前查询条件，只替换 page 参数，供分页组件使用。"""
            args = request.args.to_dict(flat=True)
            args["page"] = target_page
            view_args = {
                key: value
                for key, value in (request.view_args or {}).items()
                if value is not None
            }
            endpoint = request.endpoint or "market.index"
            return url_for(endpoint, **view_args, **args)

        return {
            "current_user": g.get("user"),
            "nav_categories": categories,
            "csrf_token": csrf_token,
            "page_url": page_url,
        }

    @app.after_request
    def set_security_headers(response):
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "SAMEORIGIN")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        return response


def _register_template_helpers(app: Flask) -> None:
    app.jinja_env.filters["price"] = format_price
    app.jinja_env.filters["timeago"] = time_ago
    app.jinja_env.filters["avatar"] = lambda name: (name or "?")[:1].upper()

    @app.template_filter("status_class")
    def status_class(status: str) -> str:
        return {"在售": "success", "已售": "secondary", "下架": "light"}.get(status, "secondary")


def _register_error_handlers(app: Flask) -> None:
    """统一错误页；Ajax 请求返回 JSON，避免把 HTML 塞进前端提示框。"""

    def wants_json() -> bool:
        return (
            request.headers.get("X-Requested-With") == "XMLHttpRequest"
            or request.accept_mimetypes.best == "application/json"
        )

    @app.errorhandler(400)
    def bad_request(error):
        message = getattr(error, "description", "请求参数有误")
        if wants_json():
            return jsonify(ok=False, msg=message), 400
        return render_template("errors/400.html", message=message), 400

    @app.errorhandler(403)
    def forbidden(_error):
        if wants_json():
            return jsonify(ok=False, msg="没有权限执行该操作"), 403
        return render_template("errors/403.html"), 403

    @app.errorhandler(404)
    def not_found(_error):
        if wants_json():
            return jsonify(ok=False, msg="资源不存在"), 404
        return render_template("errors/404.html"), 404

    @app.errorhandler(413)
    def payload_too_large(_error):
        if wants_json():
            return jsonify(ok=False, msg="上传内容过大，单次请求不能超过 12MB"), 413
        return render_template("errors/413.html"), 413

    @app.errorhandler(500)
    def server_error(_error):
        db.session.rollback()
        if wants_json():
            return jsonify(ok=False, msg="服务器开小差了，请稍后重试"), 500
        return render_template("errors/500.html"), 500
