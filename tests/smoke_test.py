"""端到端冒烟测试：覆盖注册登录、发布、搜索、收藏、留言、权限与异常场景。

前置条件：应用已启动（默认 http://127.0.0.1:5000），数据库已 seed。
运行：
    python tests/smoke_test.py
可用环境变量 BASE_URL 指定地址。
"""
import io
import os
import re
import sys
import tempfile
from pathlib import Path

import requests
from PIL import Image

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000")
PASSED = 0
FAILED = 0


def check(name: str, condition: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if condition:
        PASSED += 1
        print(f"  PASS  {name}")
    else:
        FAILED += 1
        print(f"  FAIL  {name} {detail}")


def csrf_from(html: str) -> str:
    match = re.search(r'name="csrf_token"\s+value="([^"]+)"', html)
    if not match:
        match = re.search(r'name="csrf-token" content="([^"]+)"', html)
    return match.group(1) if match else ""


def login(username: str, password: str = "123456") -> requests.Session:
    session = requests.Session()
    page = session.get(f"{BASE_URL}/auth/login", timeout=10)
    token = csrf_from(page.text)
    response = session.post(
        f"{BASE_URL}/auth/login",
        data={
            "account": username,
            "password": password,
            "csrf_token": token,
        },
        allow_redirects=False,
        timeout=10,
    )
    assert response.status_code == 302, f"登录失败: {response.status_code}"
    return session


def image_bytes(size=(640, 480), color=(80, 120, 220), fmt="JPEG") -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", size, color).save(buffer, format=fmt)
    return buffer.getvalue()


def main() -> int:
    print(f"目标地址：{BASE_URL}")

    print("\n[1] 匿名访问与公开页面")
    home = requests.get(f"{BASE_URL}/", timeout=10)
    check("首页 200", home.status_code == 200)
    check("首页渲染商品卡片", home.text.count("item-card") >= 9)
    check("首页包含价格", "¥" in home.text)

    detail = requests.get(f"{BASE_URL}/item/1", timeout=10)
    check("商品详情 200", detail.status_code == 200)
    check("详情页含留言区", "留言" in detail.text)

    missing = requests.get(f"{BASE_URL}/item/999999", timeout=10)
    check("不存在的商品返回 404", missing.status_code == 404)

    stats = requests.get(f"{BASE_URL}/stats/", timeout=10)
    check("统计页 200", stats.status_code == 200)

    for api in ("category", "trend", "price", "status"):
        response = requests.get(f"{BASE_URL}/stats/api/{api}", timeout=10)
        payload = response.json()
        check(f"统计接口 {api} 返回数据", response.status_code == 200 and payload.get("ok") is True)

    print("\n[2] 搜索、筛选与分页边界")
    for query in ("高数", "iPad", "%", "_", "'", "不存在的商品xyz"):
        response = requests.get(f"{BASE_URL}/", params={"q": query}, timeout=10)
        check(f"搜索「{query}」不报错", response.status_code == 200)

    wildcard = requests.get(f"{BASE_URL}/", params={"q": "%"}, timeout=10)
    check("LIKE 通配符被转义（% 不匹配全部）", wildcard.text.count("item-card") < 9)

    for page in ("abc", "-3", "99999", "0", "1"):
        response = requests.get(f"{BASE_URL}/", params={"page": page}, timeout=10)
        check(f"分页参数 page={page} 不报错", response.status_code == 200)

    filtered = requests.get(f"{BASE_URL}/", params={"category": "shuma", "sort": "price_asc"}, timeout=10)
    check("分类 + 排序组合可用", filtered.status_code == 200)
    check("非法分类 404", requests.get(f"{BASE_URL}/", params={"category": "nope"}).status_code == 404)

    print("\n[3] 登录与权限校验")
    anonymous = requests.Session()
    anonymous_page = anonymous.get(f"{BASE_URL}/item/1", timeout=10)
    anonymous_favorite = anonymous.post(
        f"{BASE_URL}/item/1/favorite",
        headers={
            "X-Requested-With": "XMLHttpRequest",
            "X-CSRF-Token": csrf_from(anonymous_page.text),
        },
        timeout=10,
    )
    check("未登录收藏返回 401", anonymous_favorite.status_code == 401)

    no_csrf = requests.post(f"{BASE_URL}/auth/login", data={"account": "xiaoming", "password": "123456"})
    check("缺少 CSRF 令牌返回 400", no_csrf.status_code == 400)

    seller = login("xiaoming")
    profile = seller.get(f"{BASE_URL}/me/", timeout=10)
    check("登录后可进入个人中心", profile.status_code == 200 and "个人" in profile.text)

    other = login("xiaohong")
    forbidden = other.get(f"{BASE_URL}/item/1/edit", timeout=10)
    check("非卖家编辑商品返回 403", forbidden.status_code == 403)

    print("\n[4] 收藏（判重与取消）")
    detail_page = seller.get(f"{BASE_URL}/item/4", timeout=10)
    token = csrf_from(detail_page.text)
    favorite_url = f"{BASE_URL}/item/4/favorite"
    headers = {"X-CSRF-Token": token, "X-Requested-With": "XMLHttpRequest"}

    first = seller.post(favorite_url, headers=headers, timeout=10).json()
    second = seller.post(favorite_url, headers=headers, timeout=10).json()
    check("首次收藏成功", first.get("ok") is True and first.get("favorited") is True)
    check("重复点击变为取消收藏", second.get("favorited") is False)
    third = seller.post(favorite_url, headers=headers, timeout=10).json()
    check("再次收藏可恢复", third.get("favorited") is True)

    print("\n[5] 发布商品与图片校验")
    publish_page = seller.get(f"{BASE_URL}/item/new", timeout=10)
    token = csrf_from(publish_page.text)
    base_form = {
        "csrf_token": token,
        "title": "冒烟测试：九成新机械键盘",
        "description": "自动化测试创建的商品，用于验证发布、编辑、删除闭环。",
        "price": "99.50",
        "condition": "九成新",
        "campus": "东校区",
        "category_id": "2",
    }

    too_big = seller.post(
        f"{BASE_URL}/item/new",
        data=base_form,
        files={"images": ("big.jpg", b"0" * (2 * 1024 * 1024 + 1024), "image/jpeg")},
        timeout=20,
    )
    check("超过 2MB 的图片被拒绝", too_big.status_code == 400 and "2MB" in too_big.text)

    bad_ext = seller.post(
        f"{BASE_URL}/item/new",
        data=base_form,
        files={"images": ("note.txt", b"hello world", "text/plain")},
        timeout=20,
    )
    check("非图片扩展名被拒绝", bad_ext.status_code == 400 and "格式" in bad_ext.text)

    fake_image = seller.post(
        f"{BASE_URL}/item/new",
        data=base_form,
        files={"images": ("fake.jpg", b"not really an image", "image/jpeg")},
        timeout=20,
    )
    check("伪造扩展名被内容校验拦截", fake_image.status_code == 400)

    no_image = seller.post(f"{BASE_URL}/item/new", data=base_form, timeout=10)
    check("缺少图片不能发布", no_image.status_code == 400)

    short_title = dict(base_form, title="短")
    bad_title = seller.post(
        f"{BASE_URL}/item/new",
        data=short_title,
        files={"images": ("ok.jpg", image_bytes(), "image/jpeg")},
        timeout=20,
    )
    check("标题长度校验生效", bad_title.status_code == 400 and "4~80" in bad_title.text)

    created = seller.post(
        f"{BASE_URL}/item/new",
        data=base_form,
        files={"images": ("ok.jpg", image_bytes(), "image/jpeg")},
        allow_redirects=False,
        timeout=20,
    )
    check("发布成功跳转详情页", created.status_code == 302 and "/item/" in created.headers.get("Location", ""))
    item_url = BASE_URL + created.headers["Location"]
    item_page = seller.get(item_url, timeout=10)
    check("新商品详情包含标题", "冒烟测试：九成新机械键盘" in item_page.text)

    print("\n[6] 编辑、改状态、删除")
    edit_page = seller.get(f"{item_url}/edit", timeout=10)
    token = csrf_from(edit_page.text)
    keep_id = re.search(r'name="keep_image"\s+value="(\d+)"', edit_page.text)
    updated = seller.post(
        f"{item_url}/edit",
        data={
            "csrf_token": token,
            "title": "冒烟测试：机械键盘（已编辑）",
            "description": "已修改描述，验证编辑保存逻辑正常。",
            "price": "88.00",
            "condition": "八成新",
            "campus": "西校区",
            "category_id": "2",
            "keep_image": keep_id.group(1) if keep_id else "",
        },
        allow_redirects=False,
        timeout=20,
    )
    check("编辑保存成功", updated.status_code == 302)
    check("编辑后标题生效", "已编辑" in seller.get(item_url, timeout=10).text)

    token = csrf_from(seller.get(item_url, timeout=10).text)
    status_change = seller.post(
        f"{item_url}/status", data={"csrf_token": token, "status": "已售"}, allow_redirects=False
    )
    check("修改商品状态成功", status_change.status_code == 302)
    check("状态显示为已售", "已售" in seller.get(item_url, timeout=10).text)

    stolen_delete = other.post(
        f"{item_url}/delete",
        data={"csrf_token": csrf_from(other.get(item_url, timeout=10).text)},
    )
    check("非卖家不能删除商品", stolen_delete.status_code == 403)

    deleted = seller.post(
        f"{item_url}/delete",
        data={"csrf_token": csrf_from(seller.get(item_url, timeout=10).text)},
        allow_redirects=False,
    )
    check("卖家删除商品成功", deleted.status_code == 302)
    check("删除后详情 404", seller.get(item_url, timeout=10).status_code == 404)

    print("\n[7] 留言与卖家回复")
    target_item = "/item/1"  # 卖家为 xiaoming
    buyer_page = other.get(f"{BASE_URL}{target_item}", timeout=10)
    token = csrf_from(buyer_page.text)
    posted = other.post(
        f"{BASE_URL}{target_item}/message",
        data={"csrf_token": token, "content": "冒烟测试留言：请问还在吗？"},
        allow_redirects=False,
    )
    check("登录用户可留言", posted.status_code == 302)
    check("留言展示在详情页", "冒烟测试留言" in other.get(f"{BASE_URL}{target_item}", timeout=10).text)

    seller_page = seller.get(f"{BASE_URL}{target_item}", timeout=10)
    message_id = re.search(r'/message/(\d+)/reply', seller_page.text)
    check("卖家能看到回复框", message_id is not None)
    if message_id:
        replied = seller.post(
            f"{BASE_URL}/message/{message_id.group(1)}/reply",
            data={"csrf_token": csrf_from(seller_page.text), "content": "冒烟测试回复：还在的。"},
            allow_redirects=False,
        )
        check("卖家回复成功", replied.status_code == 302)
        check("回复展示在详情页", "冒烟测试回复" in seller.get(f"{BASE_URL}{target_item}", timeout=10).text)

    buyer_reply = other.post(
        f"{BASE_URL}/message/{message_id.group(1)}/reply" if message_id else f"{BASE_URL}/message/1/reply",
        data={"csrf_token": csrf_from(other.get(f"{BASE_URL}{target_item}", timeout=10).text), "content": "非卖家回复"},
    )
    check("非卖家不能回复留言", buyer_reply.status_code == 403)

    print(f"\n结果：{PASSED} 项通过，{FAILED} 项失败")
    return 0 if FAILED == 0 else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except Exception as exc:  # noqa: BLE001 - 测试脚本直接打印异常
        print(f"\n测试异常终止：{type(exc).__name__}: {exc}")
        sys.exit(2)
