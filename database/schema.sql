-- ============================================================================
-- 校园集市（SK3017 课程设计 · 题目二）数据库初始化脚本
-- 数据库：MySQL 8.0 / utf8mb4
-- 说明：本脚本只负责建库建表；演示数据请用 `flask --app run.py seed-db` 生成
--       （种子数据需要同时生成本地图片文件，纯 SQL 无法完成）。
-- 执行：mysql -uroot -p < database/schema.sql
-- ============================================================================

CREATE DATABASE IF NOT EXISTS sk3017_market
    DEFAULT CHARACTER SET utf8mb4
    COLLATE utf8mb4_unicode_ci;

USE sk3017_market;

SET NAMES utf8mb4;
SET FOREIGN_KEY_CHECKS = 0;

DROP TABLE IF EXISTS messages;
DROP TABLE IF EXISTS favorites;
DROP TABLE IF EXISTS item_images;
DROP TABLE IF EXISTS items;
DROP TABLE IF EXISTS categories;
DROP TABLE IF EXISTS users;

SET FOREIGN_KEY_CHECKS = 1;

-- ---------------------------------------------------------------------------
-- 用户表
-- ---------------------------------------------------------------------------
CREATE TABLE users (
    id            INT           NOT NULL AUTO_INCREMENT COMMENT '主键',
    username      VARCHAR(32)   NOT NULL COMMENT '用户名（登录名，唯一）',
    email         VARCHAR(120)  NOT NULL COMMENT '邮箱（唯一）',
    password_hash VARCHAR(255)  NOT NULL COMMENT 'Werkzeug 密码哈希',
    phone         VARCHAR(20)   DEFAULT '' COMMENT '手机号（选填）',
    campus        VARCHAR(64)   DEFAULT '' COMMENT '所在校区',
    bio           VARCHAR(200)  DEFAULT '' COMMENT '个人签名',
    created_at    DATETIME      NOT NULL COMMENT '注册时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_users_username (username),
    UNIQUE KEY uq_users_email (email)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '用户表';

-- ---------------------------------------------------------------------------
-- 商品分类表
-- ---------------------------------------------------------------------------
CREATE TABLE categories (
    id         INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
    name       VARCHAR(32)  NOT NULL COMMENT '分类名称',
    slug       VARCHAR(32)  NOT NULL COMMENT 'URL 标识',
    icon       VARCHAR(16)  DEFAULT '📦' COMMENT '分类图标（emoji）',
    sort_order INT          DEFAULT 0 COMMENT '排序值，越小越靠前',
    PRIMARY KEY (id),
    UNIQUE KEY uq_categories_name (name),
    UNIQUE KEY uq_categories_slug (slug)
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '商品分类表';

-- ---------------------------------------------------------------------------
-- 商品表
-- ---------------------------------------------------------------------------
CREATE TABLE items (
    id          INT            NOT NULL AUTO_INCREMENT COMMENT '主键',
    title       VARCHAR(80)    NOT NULL COMMENT '商品标题',
    description TEXT           NOT NULL COMMENT '商品描述',
    price       DECIMAL(10, 2) NOT NULL COMMENT '价格（元）',
    `condition` VARCHAR(16)    NOT NULL DEFAULT '九成新' COMMENT '成色：全新/九成新/八成新/有使用痕迹',
    campus      VARCHAR(64)    DEFAULT '' COMMENT '交易校区',
    status      VARCHAR(8)     NOT NULL DEFAULT '在售' COMMENT '状态：在售/已售/下架',
    views       INT            NOT NULL DEFAULT 0 COMMENT '浏览量',
    seller_id   INT            NOT NULL COMMENT '发布者',
    category_id INT            NOT NULL COMMENT '分类',
    created_at  DATETIME       NOT NULL COMMENT '发布时间',
    updated_at  DATETIME       NOT NULL COMMENT '最后编辑时间',
    PRIMARY KEY (id),
    KEY ix_items_seller_id (seller_id),
    KEY ix_items_category_id (category_id),
    KEY ix_items_status (status),
    KEY ix_items_created_at (created_at),
    CONSTRAINT fk_items_seller FOREIGN KEY (seller_id) REFERENCES users (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_items_category FOREIGN KEY (category_id) REFERENCES categories (id)
        ON DELETE RESTRICT
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '商品表';

-- ---------------------------------------------------------------------------
-- 商品图片表（一个商品 1~3 张）
-- ---------------------------------------------------------------------------
CREATE TABLE item_images (
    id         INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
    item_id    INT          NOT NULL COMMENT '所属商品',
    filename   VARCHAR(120) NOT NULL COMMENT '存储文件名（UUID.jpg）',
    sort_order INT          DEFAULT 0 COMMENT '展示顺序，0 为封面',
    PRIMARY KEY (id),
    KEY ix_item_images_item_id (item_id),
    CONSTRAINT fk_item_images_item FOREIGN KEY (item_id) REFERENCES items (id)
        ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '商品图片表';

-- ---------------------------------------------------------------------------
-- 收藏表（user_id + item_id 唯一，天然防重复收藏）
-- ---------------------------------------------------------------------------
CREATE TABLE favorites (
    id         INT      NOT NULL AUTO_INCREMENT COMMENT '主键',
    user_id    INT      NOT NULL COMMENT '收藏人',
    item_id    INT      NOT NULL COMMENT '被收藏商品',
    created_at DATETIME NOT NULL COMMENT '收藏时间',
    PRIMARY KEY (id),
    UNIQUE KEY uq_favorite_user_item (user_id, item_id),
    KEY ix_favorites_item_id (item_id),
    CONSTRAINT fk_favorites_user FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_favorites_item FOREIGN KEY (item_id) REFERENCES items (id)
        ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '收藏表';

-- ---------------------------------------------------------------------------
-- 留言表（parent_id 自关联：卖家对买家留言的回复）
-- ---------------------------------------------------------------------------
CREATE TABLE messages (
    id         INT          NOT NULL AUTO_INCREMENT COMMENT '主键',
    item_id    INT          NOT NULL COMMENT '所属商品',
    user_id    INT          NOT NULL COMMENT '留言人',
    parent_id  INT          DEFAULT NULL COMMENT '父留言 ID，NULL 表示买家的一级留言',
    content    VARCHAR(500) NOT NULL COMMENT '留言内容',
    created_at DATETIME     NOT NULL COMMENT '留言时间',
    PRIMARY KEY (id),
    KEY ix_messages_item_id (item_id),
    KEY ix_messages_parent_id (parent_id),
    CONSTRAINT fk_messages_item FOREIGN KEY (item_id) REFERENCES items (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_messages_user FOREIGN KEY (user_id) REFERENCES users (id)
        ON DELETE CASCADE,
    CONSTRAINT fk_messages_parent FOREIGN KEY (parent_id) REFERENCES messages (id)
        ON DELETE CASCADE
) ENGINE = InnoDB DEFAULT CHARSET = utf8mb4 COLLATE = utf8mb4_unicode_ci
  COMMENT = '留言表';
