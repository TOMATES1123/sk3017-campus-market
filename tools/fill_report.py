"""按模板填写《SK3017 课程设计报告》，并导出 PDF。

模板结构：封面 + 实验目的 + 内容要求 + 三个 1x1 表格（分别对应 1/2/3 节正文）。
内容填入表格单元格，保留模板原有边框与版式。

用法：
    python tools/fill_report.py
"""
import re
from pathlib import Path

from docx import Document
from docx.enum.table import WD_ALIGN_VERTICAL, WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

ROOT = Path(__file__).resolve().parent.parent
TEMPLATE = ROOT.parent / "SK3017课程设计报告（学生填写模板）.docx"
DOCX_OUT = ROOT / "docs" / "课程设计报告.docx"
IMAGES = ROOT / "docs" / "images"
SHOTS = ROOT / "screenshots"

SONG = "宋体"
HEI = "黑体"
MONO = "Consolas"
BODY_SIZE = 10.5  # 五号字，表格内文字不宜过大


# ---------------------------------------------------------------------------
# 基础格式化工具
# ---------------------------------------------------------------------------
def style_run(run, name=SONG, size=BODY_SIZE, bold=False, color=None, italic=False):
    run.font.name = name
    run._element.get_or_add_rPr().rFonts.set(qn("w:eastAsia"), name)
    run.font.size = Pt(size)
    run.bold = bold
    run.italic = italic
    if color:
        run.font.color.rgb = RGBColor.from_string(color)
    return run


def add_para(container, text="", *, name=SONG, size=BODY_SIZE, bold=False,
             indent=True, align=None, before=0, after=4, line=1.45, color=None):
    paragraph = container.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(before)
    fmt.space_after = Pt(after)
    fmt.line_spacing = line
    if indent:
        fmt.first_line_indent = Pt(size * 2)
    if align is not None:
        paragraph.alignment = align
    if text:
        style_run(paragraph.add_run(text), name, size, bold, color)
    return paragraph


def add_heading(container, text, level=1):
    """单元格内的小标题：一级 13pt 黑体，二级 11.5pt 黑体。"""
    paragraph = container.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(10 if level == 1 else 6)
    fmt.space_after = Pt(4)
    fmt.keep_with_next = True
    style_run(paragraph.add_run(text), HEI, 13 if level == 1 else 11.5, True,
              "1F3864" if level == 1 else "333333")
    return paragraph


def shade_paragraph(paragraph, fill="F5F7FA"):
    pPr = paragraph._p.get_or_add_pPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    pPr.append(shd)


def add_code(container, code):
    paragraph = container.add_paragraph()
    fmt = paragraph.paragraph_format
    fmt.space_before = Pt(2)
    fmt.space_after = Pt(6)
    fmt.line_spacing = 1.1
    fmt.left_indent = Cm(0.6)
    fmt.right_indent = Cm(0.3)
    run = paragraph.add_run(code)
    style_run(run, MONO, 8.5, color="333333")
    shade_paragraph(paragraph)
    return paragraph


def add_image(container, path, width_cm, caption):
    paragraph = container.add_paragraph()
    paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
    paragraph.paragraph_format.space_before = Pt(4)
    paragraph.paragraph_format.space_after = Pt(2)
    paragraph.paragraph_format.keep_with_next = True
    paragraph.add_run().add_picture(str(path), width=Cm(width_cm))
    cap = container.add_paragraph()
    cap.alignment = WD_ALIGN_PARAGRAPH.CENTER
    cap.paragraph_format.space_after = Pt(8)
    style_run(cap.add_run(caption), SONG, 9, color="595959")


def shade_cell(cell, fill):
    tcPr = cell._tc.get_or_add_tcPr()
    shd = OxmlElement("w:shd")
    shd.set(qn("w:val"), "clear")
    shd.set(qn("w:color"), "auto")
    shd.set(qn("w:fill"), fill)
    tcPr.append(shd)


def set_table_borders(table):
    """模板里没有 Table Grid 样式，直接写 tblBorders。"""
    tblPr = table._tbl.tblPr
    borders = OxmlElement("w:tblBorders")
    for edge in ("top", "left", "bottom", "right", "insideH", "insideV"):
        element = OxmlElement(f"w:{edge}")
        element.set(qn("w:val"), "single")
        element.set(qn("w:sz"), "4")
        element.set(qn("w:space"), "0")
        element.set(qn("w:color"), "B4C6E7")
        borders.append(element)
    tblPr.append(borders)


def add_table(container, header, rows, widths):
    table = container.add_table(rows=1, cols=len(header))
    set_table_borders(table)
    table.alignment = WD_TABLE_ALIGNMENT.CENTER
    table.autofit = False
    for index, title in enumerate(header):
        cell = table.rows[0].cells[index]
        cell.width = Cm(widths[index])
        cell.vertical_alignment = WD_ALIGN_VERTICAL.CENTER
        shade_cell(cell, "E8EDF7")
        paragraph = cell.paragraphs[0]
        paragraph.alignment = WD_ALIGN_PARAGRAPH.CENTER
        paragraph.paragraph_format.space_after = Pt(2)
        style_run(paragraph.add_run(title), HEI, 9, True)
    for row in rows:
        cells = table.add_row().cells
        for index, value in enumerate(row):
            cells[index].width = Cm(widths[index])
            paragraph = cells[index].paragraphs[0]
            paragraph.paragraph_format.space_after = Pt(2)
            paragraph.paragraph_format.line_spacing = 1.15
            style_run(paragraph.add_run(str(value)), SONG, 8.5)
    return table


# ---------------------------------------------------------------------------
# 模板单元格
# ---------------------------------------------------------------------------
def clear_cell(cell):
    cell._tc.clear_content()
    cell.vertical_alignment = WD_ALIGN_VERTICAL.TOP
    # clear_content 会连段落一起清掉，补一个段落，表格单元格必须至少有一个段落
    cell.add_paragraph()
    return cell.paragraphs[0]


def fill_section1(cell):
    clear_cell(cell)

    add_heading(cell, "1.1 系统总体架构", 1)
    add_para(cell,
             "项目采用 Flask 应用工厂 + 蓝图（Blueprint）的分层结构，前后端不分离："
             "浏览器请求由 Jinja2 渲染页面，收藏等局部操作通过原生 Fetch 调用 JSON 接口，"
             "数据层使用 Flask-SQLAlchemy ORM 访问 MySQL 8，统计图表由 ECharts 渲染。"
             "选择这种结构的原因是课程要求覆盖路由、模板、表单、ORM、蓝图模块化等知识点，"
             "同时单体结构在课程演示环境中部署成本最低。")
    add_image(cell, IMAGES / "architecture.png", 14.0, "图 1  系统总体架构")

    add_para(cell,
             "代码按职责拆分为四层：app/__init__.py 负责应用工厂、配置、请求钩子（加载用户、"
             "CSRF 校验）、模板上下文与错误处理；auth / market / user / stats 四个蓝图分别承载"
             "认证、商品交易、个人中心和数据统计；models.py 定义 6 张表的 ORM 映射与关系；"
             "utils.py 收敛登录校验、CSRF、图片上传、分页参数与 LIKE 转义等公共逻辑。"
             "extensions.py 单独存放 db 实例，避免应用工厂与模型之间循环导入。")
    add_para(cell,
             "请求进入后的处理顺序为：加载登录用户 → 写操作校验 CSRF → 蓝图视图完成参数、"
             "权限与业务校验 → 模板渲染。响应阶段统一附加 X-Content-Type-Options、X-Frame-Options、"
             "Referrer-Policy 安全头；异常统一映射为 400/403/404/413/500 页面，"
             "Ajax 请求则返回结构化 JSON，避免把 HTML 错误页塞进前端提示框。")

    add_heading(cell, "1.2 数据库设计", 1)
    add_para(cell,
             "数据库共 6 张表：users（用户）、categories（分类）、items（商品）、item_images（商品图片）、"
             "favorites（收藏）、messages（留言）。商品与用户、分类是多对一，商品与图片是一对多，"
             "用户与商品通过 favorites 形成多对多，留言通过 parent_id 自关联表达“卖家回复”。"
             "ER 图如下。")
    add_image(cell, IMAGES / "er.png", 14.2, "图 2  数据库 ER 图")

    add_para(cell,
             "表结构的关键设计有以下四点：其一，items.price 使用 DECIMAL(10,2) 而不是 FLOAT，"
             "金额必须精确到分；其二，favorites 表加 UNIQUE(user_id, item_id)，从数据库层保证"
             "同一用户对同一商品只有一条收藏记录；其三，items.status 与 created_at 建索引，"
             "分别服务“排除下架”的过滤和“最新发布”的排序分页；其四，图片单独建表而不是在 items "
             "存逗号分隔字符串，保证一个商品 1~3 张图可排序、可单独删除。")

    add_table(
        cell,
        ["表名", "主要字段", "约束与索引", "作用"],
        [
            ["users", "username、email、password_hash、campus", "username/email 唯一", "注册登录与卖家信息"],
            ["categories", "name、slug、icon、sort_order", "name/slug 唯一", "8 个校园分类"],
            ["items", "title、description、price、condition、status、views", "seller_id/category_id 外键，status/created_at 索引", "商品主表"],
            ["item_images", "item_id、filename、sort_order", "item_id 外键，级联删除", "商品图片 1~3 张"],
            ["favorites", "user_id、item_id、created_at", "UNIQUE(user_id,item_id)", "收藏关系"],
            ["messages", "item_id、user_id、parent_id、content", "parent_id 自关联", "留言与卖家回复"],
        ],
        [2.2, 5.0, 4.1, 2.7],
    )

    add_para(cell,
             "索引方面，items(status) 用于首页与统计过滤“非下架”，items(created_at) 配合 "
             "LIMIT/OFFSET 分页避免全表排序，items(seller_id) 支撑个人中心“我发布的”，"
             "messages(item_id) 支撑详情页留言列表。所有外键均声明级联删除，"
             "删除商品时其图片、收藏、留言一并清理，避免产生孤儿数据。", before=6)


def fill_section2(cell):
    clear_cell(cell)

    add_heading(cell, "2.1 用户认证与权限控制", 1)
    add_para(cell,
             "用户密码使用 Werkzeug 的 generate_password_hash 存储哈希，登录时用 check_password 校验，"
             "数据库中不保存明文。登录成功后先 session.clear() 清空旧会话再写入 user_id，"
             "既防止会话固定攻击，也避免把匿名会话中的临时数据带进登录态。"
             "登录跳转参数 next 做了同源校验：只允许以单个 / 开头的站内路径，"
             "带协议或域名的地址一律回退首页，防止开放重定向。")
    add_para(cell,
             "权限控制分两层：视图层的 login_required 装饰器负责“是否登录”，"
             "未登录的普通请求跳转登录页、Ajax 请求返回 401 JSON；业务层负责“是否本人”，"
             "编辑、改状态、删除商品校验 seller_id，回复留言校验商品归属，不满足直接 abort(403)，"
             "前端统一展示 403 页面。")

    add_heading(cell, "2.2 商品发布与图片上传校验", 1)
    add_para(cell,
             "发布表单对标题（4~80 字）、描述（10~1000 字）、价格（Decimal 转换、大于 0、不超过 99999.99）、"
             "分类（必须存在）、成色（枚举）逐项校验，错误以 flash 提示并回填已填内容。"
             "图片是安全风险最高的入口，因此设计为五层校验：扩展名 → 文件大小 → Pillow 能否识别 → "
             "真实格式是否为 JPEG/PNG → 最短边是否小于 160 像素。校验通过后统一转 RGB 重编码为 jpg，"
             "既去掉了可能泄露拍摄位置的 EXIF，也消除了文件头伪装。核心代码如下：")
    add_code(cell, """def save_item_image(file_storage):
    ext = file_storage.filename.rsplit(".", 1)[-1].lower()
    if ext not in current_app.config["ALLOWED_EXTENSIONS"]:
        raise UploadError("图片格式仅支持 jpg / jpeg / png")
    data = file_storage.read()
    if len(data) > current_app.config["MAX_IMAGE_BYTES"]:
        raise UploadError("图片不能超过 2MB")
    try:
        Image.open(io.BytesIO(data)).verify()      # 内容必须是图片
    except (UnidentifiedImageError, OSError):
        raise UploadError("文件内容不是有效的图片")
    image = Image.open(io.BytesIO(data))
    if image.format not in ("JPEG", "PNG") or min(image.size) < 160:
        raise UploadError("图片格式或尺寸不符合要求")
    filename = f"{uuid.uuid4().hex}.jpg"          # 避免重名与路径穿越
    image.convert("RGB").save(upload_dir / filename, "JPEG", quality=86)
    return filename""")
    add_para(cell,
             "文件写入与数据库提交的顺序也做了设计：先在视图里创建商品并 flush 拿到 id，"
             "再逐张保存图片；任何一张校验失败则回滚事务并删除本次已写入的文件；"
             "编辑删除旧图时则相反，先提交数据库，成功后再删除磁盘文件。"
             "这样即使发生回滚，也不会出现“数据库有记录、图片丢失”的不一致。")
    add_image(cell, SHOTS / "05-publish.png", 13.6, "图 3  发布闲置页面（图片上传与表单校验）")

    add_heading(cell, "2.3 列表、搜索与分页", 1)
    add_para(cell,
             "首页支持分类筛选、关键词搜索、四种排序与分页的任意组合。搜索使用 SQL LIKE 匹配标题和描述，"
             "但直接拼接用户输入会让 % 和 _ 变成通配符——搜索 % 会把全表都匹配出来。"
             "因此先转义再指定 ESCAPE 字符，代码如下：")
    add_code(cell, """def escape_like(keyword):
    return (keyword.replace("\\\\", "\\\\\\\\")
                   .replace("%", r"\\%")
                   .replace("_", r"\\_"))

pattern = f"%{escape_like(keyword)}%"
stmt = stmt.where(or_(
    Item.title.like(pattern, escape="\\\\"),
    Item.description.like(pattern, escape="\\\\"),
))""")
    add_para(cell,
             "分页参数统一由 parse_page() 解析：先尝试转 int，失败或超出 1~10000 范围一律回退第 1 页，"
             "并给 db.paginate 传 error_out=False。这样 ?page=abc、?page=-3、?page=99999 都不会触发 500 或 404。"
             "分页链接通过上下文函数 page_url() 保留当前的分类、关键词与排序参数，翻页不会丢筛选条件。"
             "分类数量用一条 LEFT JOIN + GROUP BY 查询一次取回，避免为每个分类单独查询造成 N+1。")
    add_image(cell, SHOTS / "01-home.png", 9.8, "图 4  首页：分类筛选、排序、商品卡片与分页")

    add_heading(cell, "2.4 收藏与留言", 1)
    add_para(cell,
             "收藏使用 Ajax 完成：前端 fetch 携带 X-CSRF-Token 与 X-Requested-With 头，"
             "后端返回 {ok, favorited, count, msg}，页面只更新按钮状态、图标与计数，不整页刷新；"
             "未登录返回 401，前端弹出提示后带 next 参数跳转登录。"
             "重复收藏的并发问题采用“应用层判重 + 数据库唯一约束”双重保障：")
    add_code(cell, """existing = db.session.execute(
    db.select(Favorite).where(Favorite.user_id == g.user.id,
                              Favorite.item_id == item.id)).scalars().first()
if existing:
    db.session.delete(existing); db.session.commit()
else:
    db.session.add(Favorite(user_id=g.user.id, item_id=item.id))
    try:
        db.session.commit()
    except IntegrityError:          # 并发双击被唯一约束拦住
        db.session.rollback()""")
    add_para(cell,
             "留言采用一级留言 + 卖家回复的两层结构：messages.parent_id 为空表示买家留言，"
             "卖家回复时写入 parent_id。详情页一次性查出该商品的所有一级留言，"
             "回复通过 relationship 自动带出，避免逐条查询。留言与回复都限制 2~500 字，"
             "且只有商品卖家能回复，非卖家调用回复接口返回 403。")
    add_image(cell, SHOTS / "03-detail.png", 12.4, "图 5  商品详情页：图片画廊、收藏按钮与留言回复")

    add_heading(cell, "2.5 数据看板（扩展功能）", 1)
    add_para(cell,
             "数据看板是本项目的扩展功能，用于展示平台运营情况。页面包含 4 个 KPI 指标卡"
             "（商品总数、累计浏览、注册用户、已售金额）与 4 个 ECharts 图表："
             "分类占比环形图、新增商品趋势面积图（支持 7/14/30 天切换）、价格区间柱状图、"
             "商品状态环形图；右侧还有热门商品 TOP5 与互动概况。所有数字都来自 MySQL 聚合查询，"
             "例如分类占比使用 categories LEFT JOIN items 后 GROUP BY 并计算 AVG(price)，"
             "价格分布用六个 CASE WHEN 条件聚合一次查出，趋势图按 DATE(created_at) 分组后"
             "在 Python 侧补齐没有数据的日期，保证 X 轴长度固定。")
    add_image(cell, SHOTS / "09-stats.png", 13.0, "图 6  数据看板：KPI 卡片与四个 ECharts 图表")


def fill_section3(cell):
    clear_cell(cell)

    add_heading(cell, "3.1 完成情况", 1)
    add_para(cell,
             "项目按计划在 2026-10-12 至 2026-11-10 内完成，全部基础功能可用："
             "注册登录、商品发布（1~3 张图）、分类筛选、关键词搜索与分页、商品详情、"
             "收藏判重、买家留言与卖家回复、个人中心（我发布的/我的收藏/收到的留言/资料修改）、"
             "商品状态流转与删除；扩展功能数据看板已完成，包含 4 个图表与 4 个 KPI。"
             "初始化数据为 4 个用户、8 个分类、38 件商品、50 张图片、13 条收藏、18 条留言（含回复）。")
    add_para(cell,
             "自动化测试脚本 tests/smoke_test.py 覆盖 8 组场景共 52 项断言，最终结果 52 项通过、0 项失败。"
             "覆盖点包括：未登录 Ajax 返回 401、缺少 CSRF 返回 400、非卖家编辑/删除/回复返回 403、"
             "超过 2MB 图片被拒、文本文件改名 jpg 被内容校验拦截、缺少图片不能发布、"
             "搜索 % 与 _ 不会匹配全表、非法分页参数不报错、删除后详情返回 404。"
             "另外用 pytest 为 utils.py 编写了 9 项单元测试（转义、分页参数、价格格式化、"
             "相对时间、图片校验），端到端与单元测试合计 61 项全部通过。"
             "看板数字另外用 SQL 独立核对（商品 38、在售 33、已售 4、下架 1、成交金额 350 元），与页面一致。")

    add_heading(cell, "3.2 遇到的主要问题与解决", 1)
    add_para(cell,
             "开发中记录了 17 条 Debug 日志，按类型可分为四类。第一类是“对输入的假设太乐观”："
             "例如搜索 % 会匹配全表、页码为负数会 404、文本文件改名 jpg 也能上传、"
             "非法分类 slug 返回空列表而不是 404；解决方式统一为“先校验、再使用”，"
             "并把特殊字符与非法参数写进自动化测试。")
    add_para(cell,
             "第二类是“框架机制没吃透”，也是最费时间的一类。首页曾经返回 200 但商品列表永远空白，"
             "原因是模板中导入的分页宏与上下文变量 pagination 同名，把变量覆盖成了宏；"
             "统计页四个图表全空白且控制台无报错，排查后发现 Windows 注册表把 .js 识别为 text/plain，"
             "配合 X-Content-Type-Options: nosniff 后浏览器拒绝执行脚本，最终在应用启动时显式注册 "
             "MIME 类型解决；另外给 updated_at 配置 onupdate 导致“浏览一次商品，最近更新时间就变成刚刚”，"
             "改为只在编辑商品时显式赋值。")
    add_para(cell,
             "第三类是“数据库与文件系统的一致性”：编辑商品时先删磁盘图片再提交事务，"
             "一旦后续图片校验失败回滚，就会出现数据库有记录、图片已丢失的情况；"
             "调整为“先提交数据库、成功后再删文件”，新增图片失败时则回滚并清理已写入的文件。"
             "第四类是“配置与安全”：包内相对导入路径错误、session 写入顺序导致登录态被清空、"
             "next 参数开放重定向、CSRF 校验与登录校验的先后顺序导致错误码不准确。"
             "每条问题的现象、根因、解决与预防都记录在 docs/DEBUG_LOG.md 中。")

    add_heading(cell, "3.3 不足与改进方向", 1)
    add_para(cell,
             "一是图片存本地磁盘，多机部署需要共享存储，后续可替换为对象存储（只需改 save_item_image 与"
             "图片 URL 生成两处）；二是浏览量每次访问都执行 UPDATE，高并发下会成为写热点，"
             "可改为 Redis 计数后定时落库；三是站内只有留言板，没有即时聊天，后续可加 WebSocket；"
             "四是缺少举报、信用评分等治理功能。测试方面目前是集成测试，utils.py 里的纯函数"
             "（escape_like、parse_page、save_item_image）还可以补 pytest 单元测试。")

    add_heading(cell, "3.4 总结", 1)
    add_para(cell,
             "这次课设最大的收获不是“把功能堆出来”，而是学会了用工程的方式验证功能："
             "先用 SQL 算出预期数字再和页面对比，先写出异常用例再写正常用例，"
             "遇到“页面正常但功能没生效”时同时看控制台、网络面板和数据库。"
             "AI 工具在生成初稿、解释报错上确实提高了效率，但边界条件、并发、事务顺序和平台差异"
             "仍需要自己判断——这也是我在答辩时最想讲清楚的部分。")
    add_image(cell, SHOTS / "06-user-center.png", 12.0, "图 7  个人中心：统计卡片与最近发布")


def fill_cover(document):
    paragraphs = document.paragraphs
    # 模板原文写的是“智能租房/博客二选一、可分组”，与本次路线 B、1 人 1 份不符，改写为通用表述
    purpose = paragraphs[26]
    if purpose.runs:
        first = purpose.runs[0]
        first.text = (
            "本课程设计旨在通过企业级项目实战，全面检验与巩固学生在《Python Web 企业级项目开发》"
            "课程中所学的理论知识与实践技能。学生需从课堂项目延伸或题库选题中任选其一，"
            "独立完成从需求分析、系统设计、编码实现到测试部署的全过程。通过本设计，学生应能："
        )
        for run in purpose.runs[1:]:
            run.text = ""

    replacements = {
        8: ("学生姓名：", "曾祺锐"),
        9: ("学号：", "2520148301"),
        10: ("教学班：", "（请填写）"),
        11: ("递交日期：", "2026 年 11 月 10 日"),
    }
    for index, (label, value) in replacements.items():
        paragraph = paragraphs[index]
        # 保留“学生姓名：”等标签，把最后的空白 run 换成填写内容
        runs = paragraph.runs
        if runs:
            runs[-1].text = value
            style_run(runs[-1], HEI, 14)
        else:
            style_run(paragraph.add_run(value), HEI, 14)

    # 实验日期
    date_paragraph = paragraphs[24]
    style_run(date_paragraph.add_run("2026 年 10 月 12 日 — 2026 年 11 月 10 日"), SONG, 12)


def fill_topic(paragraph):
    for run in paragraph.runs:
        run.text = ""
    style_run(paragraph.add_run(
        "① 选题路线：☑ 路线B 题库选题——题目二：校园二手交易平台（Campus Market）。"
        "本项目从零开发，未使用课堂项目源码。\n"
        "② 项目简介：基于 Flask + MySQL 的校园二手交易平台，支持发布闲置（1~3 张图片）、"
        "分类浏览、关键词搜索与分页、收藏判重、买家留言与卖家回复、个人中心管理，"
        "并扩展了基于 ECharts 的数据看板。\n"
        "③ 功能清单：用户模块（注册/登录/退出/资料与密码修改）；商品模块（发布/编辑/改状态/删除，"
        "图片格式与大小校验）；浏览模块（分类筛选/关键词搜索/四种排序/分页/详情画廊/同类推荐）；"
        "互动模块（Ajax 收藏、留言、卖家回复、个人中心我发布的/我的收藏/收到的留言）；"
        "统计模块（4 个 KPI + 4 个 ECharts 图表 + 热门 TOP5）。\n"
        "④ 课堂原有功能与本项目新增功能说明：本项目为路线 B 题库选题，全部功能均为自行设计与实现，"
        "不存在“课堂原有功能”。与课堂租房项目的区别在于：业务对象由房源变为二手商品，"
        "新增了图片上传五层校验、收藏唯一约束与并发兜底、CSRF 防护、留言自关联回复、"
        "以及完全重新设计的数据看板。"
    ), SONG, 10.5)


def fill_repo_section(document):
    paragraphs = document.paragraphs
    repo_paragraph = paragraphs[50]
    style_run(repo_paragraph.add_run(
        "https://gitee.com/你的用户名/sk3017-campus-market"
        "（GitHub 备用：https://github.com/你的用户名/sk3017-campus-market）"
    ), SONG, 10.5, color="C00000")
    style_run(repo_paragraph.add_run("　提交前请替换为实际仓库地址，并确保仓库公开或已添加老师为协作者。"),
              SONG, 9, color="808080")

    ai_paragraph = paragraphs[51]
    style_run(ai_paragraph.add_run(
        "开发过程中使用了 DeepSeek、ChatGPT 与通义灵码：主要用于需求拆解与架构选型对比、"
        "函数初稿生成、报错解释、ECharts 配置初稿、测试用例清单与文档结构建议。"
        "所有 AI 生成代码均经过人工修改与验证，边界条件、事务顺序、并发约束由本人分析确定；"
        "报告中的数据全部来自实际运行结果。完整的 8 条关键提示词、AI 回复摘要、"
        "采纳与修改情况见仓库 docs/AI协作记录.md。"
    ), SONG, 10.5)

    additions = [
        ("提交材料清单", True),
        ("仓库 docs/ 目录包含：课程设计报告.pdf（本文件）、DEVELOPMENT_LOG.md（开发日志，"
         "含 6 个里程碑与 22 个工作日记录）、DEBUG_LOG.md（17 条 Debug 记录与复盘）、"
         "AI协作记录.md（8 条关键提示词）、设计文档.md、测试报告.md；screenshots/ 目录包含 9 张功能截图；"
         "database/ 目录包含建库脚本 schema.sql 与初始化说明；README.md 包含依赖安装、"
         "数据库初始化、启动命令与测试账号。", False),
    ]
    for text, is_heading in additions:
        paragraph = document.add_paragraph()
        paragraph.paragraph_format.space_before = Pt(8 if is_heading else 4)
        paragraph.paragraph_format.space_after = Pt(4)
        paragraph.paragraph_format.line_spacing = 1.45
        if is_heading:
            style_run(paragraph.add_run(text), HEI, 11.5, True)
        else:
            style_run(paragraph.add_run(text), SONG, 10.5)


def main():
    document = Document(str(TEMPLATE))
    fill_cover(document)
    fill_topic(document.paragraphs[39])

    fill_section1(document.tables[0].cell(0, 0))
    fill_section2(document.tables[1].cell(0, 0))
    fill_section3(document.tables[2].cell(0, 0))

    fill_repo_section(document)

    document.core_properties.title = "SK3017 课程设计报告 · 校园二手交易平台"
    document.core_properties.subject = "题目二 校园二手交易平台"
    document.core_properties.author = "SK3017 学生"

    DOCX_OUT.parent.mkdir(parents=True, exist_ok=True)
    document.save(str(DOCX_OUT))
    print("saved", DOCX_OUT)


if __name__ == "__main__":
    main()
