"""SQLAlchemy 声明式基类。"""
from sqlalchemy.orm import declarative_base

# 统一的 ORM 基类，供所有模型继承
Base = declarative_base()
