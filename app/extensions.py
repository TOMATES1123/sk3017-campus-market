"""Flask 扩展实例。

单独放一个模块，避免 app 工厂与模型之间循环导入。
"""
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()
