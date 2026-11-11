# 数据库初始化说明

## 一、建库建表

```bash
mysql -uroot -p < database/schema.sql
```

脚本会创建 `sk3017_market` 数据库（utf8mb4）以及 6 张表：

| 表名 | 说明 | 关键约束 |
|---|---|---|
| `users` | 用户 | `username`、`email` 唯一 |
| `categories` | 商品分类 | `name`、`slug` 唯一 |
| `items` | 商品 | `seller_id`、`category_id` 外键；`status`、`created_at` 索引 |
| `item_images` | 商品图片 | `item_id` 外键，级联删除 |
| `favorites` | 收藏 | `UNIQUE(user_id, item_id)` 防重复收藏 |
| `messages` | 留言 | `parent_id` 自关联，级联删除 |

## 二、写入演示数据

```bash
# 先按 .env.example 配好 .env
flask --app run.py seed-db
```

`seed-db` 会重建表并写入 4 个用户、8 个分类、38 件商品、50 张商品图、13 条收藏、10 组留言，
同时用 Pillow 在 `app/static/uploads/items/` 生成占位商品图（不需要外部图片素材）。
因为图片是运行时生成的文件，所以演示数据没有做成纯 `.sql`。

## 三、只重建表结构（保留数据）

```bash
flask --app run.py init-db
```

## 四、清空数据库

```bash
flask --app run.py drop-db
```
