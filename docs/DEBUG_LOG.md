# 校园集市（题目二）Debug 日志

> 每条记录四件事：**现象（怎么错的）→ 根因（为什么错）→ 解决（改了什么）→ 预防（下次怎么不踩）**。
> 编号格式：`BUG-xxx ｜ 日期 ｜ 一句话现象标题`。按发生时间排序。

---

## BUG-001 ｜ 10-12 ｜ 启动报 ModuleNotFoundError: No module named 'app.config'

- **现象**：`flask --app run.py init-db` 启动失败，栈信息指到 `app/__init__.py` 的 `from .config import Config`。
- **根因**：`config.py` 写在了项目根目录，但 `app/__init__.py` 用的是包内相对导入 `.config`；根目录的 `config.py` 不属于 `app` 包，自然找不到。
- **解决**：把配置挪进包里 `app/config.py`，`BASE_DIR` 用 `Path(__file__).resolve().parent.parent` 指回项目根，`.env` 仍从根目录读取。
- **预防**：Python 包的导入路径只有"包内相对导入"和"顶层绝对导入"两种，配置/工具模块要么全放包内，要么全放根目录，不要混着用。

## BUG-002 ｜ 10-13 ｜ 注册成功后仍提示"请先登录"

- **现象**：注册接口返回 302 跳首页，但导航栏还是"登录 / 注册"，个人中心被重定向回登录页。
- **根因**：代码顺序写反了：
  ```python
  session["user_id"] = user.id
  session.clear()          # 把自己刚写入的登录态清掉了
  ```
- **解决**：先 `session.clear()`（清掉旧的匿名会话，防会话固定），再写 `session["user_id"]`。
- **预防**："登录成功后重建会话"是一个固定套路：**clear → 写 user_id → 设置 permanent**，三步顺序不能换。

## BUG-003 ｜ 10-14 ｜ `?next=https://example.com` 把用户带到外站

- **现象**：未登录访问受保护页会带 `?next=`，手工把 next 改成外站地址后，登录成功直接跳到了外站。
- **根因**：`redirect(request.args.get("next"))` 对参数零校验，形成开放重定向（可被用于钓鱼）。
- **解决**：加 `_safe_next()`：用 `urlsplit` 解析，只要带 scheme 或 netloc、或以 `//` 开头，一律跳回首页；只允许站内相对路径。
- **预防**：所有"从 URL 取跳转目标"的地方都必须做白名单校验，这是 OWASP 的固定检查项。

## BUG-004 ｜ 10-15 ｜ 访问 `?page=-3` 列表页直接 404

- **现象**：首页正常，但 `/?page=-3` 返回 404 页面（Flask-SQLAlchemy 的 `paginate` 默认 `error_out=True`）。
- **根因**：`page` 直接传给 `db.paginate`，负数/0/超大值都会触发分页器自身的错误处理，而不是回退到第 1 页。
- **解决**：统一用 `parse_page()` 解析：
  ```python
  def parse_page(raw, default=1, max_page=10000):
      try:
          page = int(str(raw))
      except (TypeError, ValueError):
          return default
      return page if 1 <= page <= max_page else default
  ```
  同时 `db.paginate(..., error_out=False)`。
- **预防**：凡是来自 URL 的整数参数，先"类型转换 + 范围校验 + 默认值"三连，不要直接进 ORM。

## BUG-005 ｜ 10-20 ｜ 上传 3MB 图片页面白屏（413）

- **现象**：发布页选一张 3MB 图，提交后浏览器显示 Flask 默认 413 页面，而不是站内提示。
- **根因**：`MAX_CONTENT_LENGTH` 只设了全局 12MB，业务层的 2MB 限制在读到文件后才判断；3MB 的请求体在进入视图前就被 Werkzeug 拒绝，没有自定义处理。
- **解决**：注册 413 错误处理器，返回站内 `errors/413.html`（Ajax 返回 JSON）；前端在选择文件时先判断 `file.size > 2MB` 并提示，减少无效请求。
- **预防**：请求体限制是"网关层"错误，必须有对应的错误页；前端预校验只能减少请求，不能替代服务端校验。

## BUG-006 ｜ 10-20 ｜ 把 note.txt 改名成 note.jpg 也能上传成功

- **现象**：测试上传时把文本文件后缀改成 `.jpg`，商品发布成功，详情页显示裂图。
- **根因**：第一版只校验扩展名，没有校验文件内容。
- **解决**：加 Pillow 内容校验：`Image.open(...).verify()` 识别失败即拒绝；再用 `image.format in ("JPEG","PNG")` 校验真实格式；最后统一重编码为 jpg。
- **预防**：文件上传永远"不要相信客户端给的扩展名和 Content-Type"，用内容嗅探 + 重编码。

## BUG-007 ｜ 10-21 ｜ 编辑商品删图失败后，数据库有记录、文件却没了

- **现象**：编辑商品时删除一张旧图并上传一张超大图，提交后提示"图片超过 2MB"，但回到编辑页旧图已经打不开（404）。
- **根因**：代码先 `remove_item_image()` 删磁盘文件，再提交事务；后续图片校验抛异常触发 `rollback`，数据库回滚了，磁盘文件却删掉了。
- **解决**：调整为"**先数据库、后文件**"：
  1. 记录待删文件名；
  2. `db.session.delete()` + `commit()`；
  3. 提交成功后再删磁盘文件。
  新增图片同理：先保存文件、失败则回滚并删除刚保存的文件。
- **预防**：涉及"数据库 + 文件系统"两个存储时，先提交不可回滚的一方（数据库），文件删除放到最后，并接受"少量孤儿文件"比"数据丢文件"更安全。

## BUG-008 ｜ 10-22 ｜ 生成演示图报 Pillow 坐标错误

- **现象**：`flask seed-db` 报 `TypeError: coordinate list must contain exactly 2 coordinates`，改完又报 `ValueError: x1 must be greater than or equal to x0`。
- **根因**：两个问题叠加：
  1. `ImageDraw.ellipse()` 需要左上/右下 4 个坐标，我只传了圆心；
  2. 装饰圆的偏移用了全局图片序号 `variant`（1~50），`x0 = -160 + variant*40` 很快超过 `x1=200`。
- **解决**：改成 `(-160 + offset, -220, 200, 140)` 的 4 元组，`offset = (variant % 8) * 18` 限制在循环范围内。
- **预防**：调用绘图/第三方 API 前先看函数签名；任何"用序号做偏移"的地方都要取模或 clamp。

## BUG-009 ｜ 10-23 ｜ 首页 200 但商品列表永远空白

- **现象**：首页返回 200，分类数量和 hero 统计都正确，但商品区显示"没有找到相关闲置"，"共 件"里的数字也是空的。
- **根因**：模板里同时存在变量 `pagination` 和宏 `pagination`：
  ```jinja
  {% from "macros/ui.html" import item_card, pagination %}
  ...
  {{ pagination(pagination) }}
  ```
  `import` 把上下文里的分页对象覆盖成了宏，`pagination.items` 自然为空。
- **解决**：宏改名为 `render_pagination`，所有模板同步替换。
- **预防**：给 Jinja 宏起"动词/渲染类"名字（render_xxx / show_xxx），不要和业务变量重名；页面"结构正常但数据为空"时优先怀疑变量被覆盖。

## BUG-010 ｜ 10-26 ｜ 搜索 `%` 返回全部商品

- **现象**：搜索框输入 `%`，结果列表把 38 件商品全列出来了；输入 `_` 也会匹配大量商品。
- **根因**：SQL `LIKE` 中 `%` 和 `_` 是通配符，直接拼进 `f"%{keyword}%"` 后语义被改变。
- **解决**：新增 `escape_like()` 转义 `\ % _`，并在 `like()` 上显式指定 `escape="\\"`。
- **预防**：所有把用户输入拼进 LIKE 的地方都要转义；测试用例固定加 `%`、`_`、`'`、`\` 四个特殊字符。

## BUG-011 ｜ 10-26 ｜ 分页宏报 `'page_url' is undefined`

- **现象**：首页列表能出来，但一渲染分页组件就 500，报 `jinja2.exceptions.UndefinedError: 'page_url' is undefined`。
- **根因**：`page_url` 是 `context_processor` 注入的上下文函数，而 `{% from "macros/ui.html" import ... %}` 默认**不传递上下文**，宏内部拿不到它。
- **解决**：改为 `{% from "macros/ui.html" import item_card, render_pagination with context %}`。
- **预防**：宏里用到 `url_for` 之外的上下文变量（current_user、自定义函数）时，导入必须加 `with context`。

## BUG-012 ｜ 10-27 ｜ 浏览商品后"最近更新"变成"刚刚"

- **现象**：详情页每次刷新浏览量 +1，但"最近更新"也跟着变成"刚刚"，即使内容没有任何修改。
- **根因**：`Item.updated_at` 上配了 `onupdate=datetime.now`，任何 UPDATE（包括 `views = views + 1`）都会刷新它。
- **解决**：去掉模型上的 `onupdate`，在编辑商品的视图里显式 `item.updated_at = datetime.now()`。
- **预防**：ORM 的 `onupdate` 是"行级"而不是"业务级"的，凡是"仅部分字段变更才算更新"的语义，都要显式赋值。

## BUG-013 ｜ 10-14 ｜ 未登录 Ajax 收藏返回 400 而不是 401

- **现象**：未登录点收藏，前端提示"页面已过期，请刷新"，而不是"请先登录"。
- **根因**：`before_request` 中 CSRF 校验注册在登录加载之后、视图之前，匿名请求本来就没有令牌，先被 CSRF 拦成 400。
- **解决**：测试用例改为"先 GET 详情页拿令牌再 POST"，验证登录校验返回 401；同时前端对 401 统一跳登录。保持"CSRF 先于业务"的顺序不变（登录表单本身也需要 CSRF 保护）。
- **预防**：区分"认证失败"和"请求被篡改"两类错误码；匿名 Ajax 请求要先拿到页面令牌，否则无法区分。

## BUG-014 ｜ 10-28 ｜ 连续点两次收藏出现两条记录

- **现象**：详情页快速双击收藏按钮，个人中心"我的收藏"出现两条同一商品。
- **根因**：应用层"先查再插"不是原子操作，两个并发请求都查到"没有"，都执行了插入。
- **解决**：数据库层加 `UNIQUE(user_id, item_id)`；插入捕获 `IntegrityError` 后 `rollback()`，按"已收藏"返回并提示"该商品已在收藏列表中"。
- **预防**：幂等写操作要让数据库兜底（唯一约束/幂等键），应用层判重只负责友好提示。

## BUG-015 ｜ 11-03 ｜ 统计页四个图表全空白，控制台无报错

- **现象**：`/stats` 页面布局正常，但四个图表区域全白；控制台没有红色报错，`typeof echarts` 是 `undefined`。
- **根因**：Windows 注册表把 `.js` 的 MIME 映射成了 `text/plain`，Flask 静态文件按系统 mimetypes 返回 `Content-Type: text/plain`；我们又设置了 `X-Content-Type-Options: nosniff`，浏览器因此拒绝执行脚本。请求状态是 200，所以网络面板看起来"一切正常"。
- **解决**：应用启动时显式注册 MIME：
  ```python
  mimetypes.add_type("application/javascript", ".js")
  mimetypes.add_type("text/css", ".css")
  ```
  重启后 `Content-Type: application/javascript`，图表恢复。
- **预防**：静态资源 200 但脚本不生效时，先看响应头 `Content-Type`；`nosniff` 是双刃剑，跨平台部署要显式声明 MIME。

## BUG-016 ｜ 11-04 ｜ 趋势图曲线与日期轴错位

- **现象**：最近 7 天趋势图，X 轴有 7 个日期，但曲线只有 5 个点，整体左移，最近两天的数据对不上。
- **根因**：SQL `GROUP BY DATE(created_at)` 只返回"有商品"的日期；没有商品的日期缺失，前端按下标一一对应就错位。
- **解决**：Python 侧按日期范围补 0：
  ```python
  counts = {str(day): int(count) for day, count in rows}
  labels, values = [], []
  for offset in range(days):
      day = start + timedelta(days=offset)
      labels.append(day.strftime("%m-%d"))
      values.append(counts.get(str(day), 0))
  ```
- **预防**：时间序列类图表，**先对齐日期轴再塞数据**；数据库聚合结果天然稀疏，补齐是必做步骤。

## BUG-017 ｜ 11-06 ｜ 非法分类 `?category=nope` 返回空列表而不是 404

- **现象**：手动改 URL 成不存在的分类，页面正常 200，显示"这个分类还空着"，容易被误认为分类存在但没商品。
- **根因**：视图直接把 slug 拼进查询条件，没有先校验分类是否存在。
- **解决**：先按 slug 查 `Category`，查不到 `abort(404)`；同时把 `active_category` 传给模板显示分类名。
- **预防**：URL 中的业务标识（分类 slug、用户名）先做存在性校验，再进入列表查询。

---

## 复盘小结

17 条记录大致分四类：

1. **对输入/数据的假设太乐观**（BUG-004/006/010/017）：页码、文件内容、LIKE 通配符、非法 slug。共性是"相信客户端"，解决方式都是"先校验、再使用"。
2. **框架机制没吃透**（BUG-009/011/012/015）：Jinja 宏覆盖变量、import 不带上下文、ORM `onupdate` 的作用范围、静态文件 MIME。这类问题不报错，最费时间，收获也最大。
3. **两个存储的一致性问题**（BUG-005/007/014）：请求体限制、数据库与磁盘文件、并发唯一约束。结论是先提交数据库、文件操作放最后、约束交给数据库。
4. **配置与安全**（BUG-001/002/003/013）：包导入路径、会话重建顺序、开放重定向、CSRF 与认证的错误码顺序。

下一阶段的改进：把"URL 参数三连校验""上传五层校验""时间序列补齐""唯一约束兜底"四条写进自己的开发 checklist；
写图表/分页类功能时，先用 SQL 算预期值，再和页面比对，避免"看起来正常"的静默错误。
