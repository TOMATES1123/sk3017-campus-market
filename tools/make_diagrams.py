"""生成报告用示意图：系统架构图、ER 图、功能结构图。

纯 Pillow 绘制，输出到 docs/images/。
用法：python tools/make_diagrams.py
"""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "images"
FONT = r"C:\Windows\Fonts\msyh.ttc"
FONT_BOLD = r"C:\Windows\Fonts\msyhbd.ttc"

INK = "#1f2937"
MUTED = "#6b7280"
LINE = "#94a3b8"
BRAND = "#4f46e5"
BRAND_SOFT = "#eef2ff"
GREEN = "#0f766e"
GREEN_SOFT = "#ecfdf5"
ORANGE = "#c2410c"
ORANGE_SOFT = "#fff7ed"
BG = "#ffffff"


def font(size: int, bold: bool = False):
    return ImageFont.truetype(FONT_BOLD if bold else FONT, size)


def box(draw, xy, title, lines, fill="#ffffff", border=LINE, title_color=INK,
        radius=14, width=2):
    x0, y0, x1, y1 = xy
    draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=border, width=width)
    draw.text((x0 + 20, y0 + 14), title, font=font(25, True), fill=title_color)
    y = y0 + 52
    for line in lines:
        draw.text((x0 + 20, y), line, font=font(19), fill=MUTED)
        y += 30


def arrow(draw, start, end, color=BRAND, width=3, label=None, label_offset=(0, -28)):
    draw.line([start, end], fill=color, width=width)
    # 箭头三角
    import math

    angle = math.atan2(end[1] - start[1], end[0] - start[0])
    size = 13
    left = (end[0] - size * math.cos(angle - 0.45), end[1] - size * math.sin(angle - 0.45))
    right = (end[0] - size * math.cos(angle + 0.45), end[1] - size * math.sin(angle + 0.45))
    draw.polygon([end, left, right], fill=color)
    if label:
        draw.text((end[0] + label_offset[0], end[1] + label_offset[1]), label,
                  font=font(17), fill=MUTED)


def architecture():
    image = Image.new("RGB", (1600, 1050), BG)
    draw = ImageDraw.Draw(image)
    draw.text((60, 40), "校园集市系统架构", font=font(38, True), fill=INK)
    draw.text((60, 92), "Flask 应用工厂 + 蓝图分层 + SQLAlchemy ORM + MySQL 8",
              font=font(21), fill=MUTED)

    box(draw, (60, 160, 420, 320), "浏览器 / 移动端",
        ["Jinja2 服务端渲染页面", "Bootstrap 5 响应式布局", "ECharts 5 图表",
         "原生 JS：收藏 Ajax / 图片预览"], fill=BRAND_SOFT, border="#c7d2fe")

    box(draw, (560, 150, 1060, 340), "Flask 应用（app/__init__.py）",
        ["应用工厂 create_app()", "before_request：加载用户 / CSRF 校验",
         "蓝图：auth · market · user · stats", "统一错误处理 400/403/404/413/500"],
        fill="#ffffff", border=BRAND, title_color=BRAND)

    box(draw, (1200, 160, 1540, 310), "静态资源",
        ["app/static/css/app.css", "app/static/js/app.js", "vendor：Bootstrap / ECharts",
         "uploads：商品图片"], fill=GREEN_SOFT, border="#99f6e4", title_color=GREEN)

    box(draw, (560, 420, 1060, 640), "业务层（蓝图视图）",
        ["auth：注册 / 登录 / 退出", "market：列表 / 搜索 / 详情 / 发布 / 收藏 / 留言",
         "user：个人中心 / 我的商品 / 收藏 / 留言 / 资料", "stats：KPI + 4 个聚合接口"],
        fill=ORANGE_SOFT, border="#fed7aa", title_color=ORANGE)

    box(draw, (560, 700, 1060, 900), "数据访问层",
        ["Flask-SQLAlchemy 3.x / SQLAlchemy 2.0 ORM",
         "模型：User / Category / Item / ItemImage",
         "Favorite（user_id+item_id 唯一约束）/ Message（自关联回复）",
         "连接池 pre_ping + recycle，防 MySQL 断连"], fill="#ffffff", border=LINE)

    box(draw, (1200, 700, 1540, 880), "MySQL 8.0",
        ["库：sk3017_market（utf8mb4）", "6 张表 + 外键 + 索引",
         "聚合：GROUP BY / COUNT / CASE"], fill="#f1f5f9", border="#cbd5e1")

    arrow(draw, (420, 240), (552, 240), label="HTTP")
    arrow(draw, (960, 340), (860, 412), label="路由分发", label_offset=(-120, 8))
    arrow(draw, (810, 640), (810, 692), label="ORM", label_offset=(18, 6))
    arrow(draw, (1060, 800), (1192, 790), label="SQL", label_offset=(18, -26))
    arrow(draw, (1060, 250), (1192, 240), color=GREEN, label="静态文件", label_offset=(12, -26))
    arrow(draw, (1200, 850), (1160, 860), color=MUTED, width=2)

    draw.text((60, 980), "说明：前后端不分离（服务端渲染 + 局部 Ajax），统计接口返回 JSON，"
                         "由 ECharts 渲染。",
              font=font(19), fill=MUTED)
    image.save(OUT / "architecture.png")


def er_diagram():
    image = Image.new("RGB", (1600, 1100), BG)
    draw = ImageDraw.Draw(image)
    draw.text((60, 36), "数据库 ER 图（6 张表）", font=font(38, True), fill=INK)
    draw.text((60, 88), "users 1—n items；categories 1—n items；items 1—n item_images；"
                        "users n—n items（favorites）；items 1—n messages（自关联回复）",
              font=font(18), fill=MUTED)

    box(draw, (50, 160, 370, 470), "users 用户",
        ["PK id", "username UNIQUE", "email UNIQUE", "password_hash",
         "phone / campus / bio", "created_at"], fill=BRAND_SOFT, border="#c7d2fe")

    box(draw, (560, 160, 930, 500), "items 商品",
        ["PK id", "FK seller_id → users.id", "FK category_id → categories.id",
         "title / description", "price DECIMAL(10,2)", "condition / campus / status",
         "views / created_at / updated_at"], fill="#ffffff", border=BRAND, title_color=BRAND)

    box(draw, (1180, 160, 1540, 360), "categories 分类",
        ["PK id", "name UNIQUE", "slug UNIQUE", "icon / sort_order"],
        fill=GREEN_SOFT, border="#99f6e4", title_color=GREEN)

    box(draw, (560, 600, 930, 860), "item_images 商品图片",
        ["PK id", "FK item_id → items.id", "filename VARCHAR(120)", "sort_order"],
        fill="#ffffff", border=LINE)

    box(draw, (60, 620, 390, 860), "favorites 收藏",
        ["PK id", "FK user_id → users.id", "FK item_id → items.id",
         "UNIQUE(user_id, item_id)", "created_at"], fill=ORANGE_SOFT,
        border="#fed7aa", title_color=ORANGE)

    box(draw, (1150, 600, 1540, 900), "messages 留言",
        ["PK id", "FK item_id → items.id", "FK user_id → users.id",
         "FK parent_id → messages.id", "content VARCHAR(500)", "created_at"],
        fill="#ffffff", border=LINE)

    arrow(draw, (370, 280), (552, 280))
    arrow(draw, (1180, 250), (938, 250))
    arrow(draw, (745, 500), (745, 592))
    arrow(draw, (400, 700), (552, 700))
    arrow(draw, (938, 760), (1142, 760))

    draw.text((60, 985),
              "关系：users 1—n items（发布）；categories 1—n items（归类）；items 1—n item_images；",
              font=font(19), fill=MUTED)
    draw.text((60, 1022),
              "users n—n items（favorites 中间表，含唯一约束）；items 1—n messages；"
              "messages 通过 parent_id 自关联表示卖家回复。",
              font=font(19), fill=MUTED)
    image.save(OUT / "er.png")


def function_map():
    image = Image.new("RGB", (1600, 900), BG)
    draw = ImageDraw.Draw(image)
    draw.text((60, 40), "系统功能结构", font=font(38, True), fill=INK)

    center = (610, 120, 990, 210)
    box(draw, center, "校园二手交易平台",
        ["Flask + MySQL + Bootstrap + ECharts"], fill=BRAND_SOFT, border=BRAND,
        title_color=BRAND)

    groups = [
        ("用户模块", ["注册 / 登录 / 退出", "个人资料与密码修改"], 70, 330),
        ("商品模块", ["发布 / 编辑 / 删除", "图片上传 1~3 张", "状态：在售/已售/下架"], 420, 330),
        ("浏览与交易", ["分类筛选 + 关键词搜索", "分页排序 / 商品详情", "收藏（判重）/ 留言回复"], 770, 330),
        ("数据统计", ["KPI 指标卡", "分类/趋势/价格/状态图表"], 1120, 330),
    ]
    for title, lines, x, y in groups:
        box(draw, (x, y, x + 330, y + 60 + 32 * len(lines)), title, lines,
            fill="#ffffff", border=LINE)
        draw.line([(800, 210), (800, 280)], fill=BRAND, width=3)
        draw.line([(x + 165, 280), (800, 280)], fill=BRAND, width=3)
        draw.line([(x + 165, 280), (x + 165, 322)], fill=BRAND, width=3)
        arrow(draw, (x + 165, 280), (x + 165, 322), color=BRAND, width=3)

    draw.text((60, 790), "扩展功能：数据看板（4 个 ECharts 图表 + 3 个 KPI 卡片）、"
                         "AJAX 收藏、CSRF 防护、图片内容校验。",
              font=font(19), fill=MUTED)
    image.save(OUT / "functions.png")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    architecture()
    er_diagram()
    function_map()
    print("diagrams saved to", OUT)
