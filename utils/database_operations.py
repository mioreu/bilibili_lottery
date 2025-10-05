import sqlite3
import logging
import os
from typing import Set

db_logger = logging.getLogger("Bilibili.Database")

def init_db(db_path: str, table_name: str = 'history') -> None:
    """
    初始化数据库
    """
    try:
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()

        # 根据传入的 table_name 创建表
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_name} (
                id TEXT PRIMARY KEY,
                type TEXT NOT NULL,
                timestamp DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')

        conn.commit()
        conn.close()
        db_logger.debug(f"数据库已成功初始化于 {db_path}，表名：{table_name}")
    except Exception as e:
        db_logger.error(f"初始化数据库失败 {db_path} (表: {table_name}): {e}", exc_info=True)


def check_id_exists(db_path: str, item_id: str, table_name: str = 'history') -> bool:
    """
    检查给定的 ID 是否已存在于指定表中
    """
    if not item_id:
        return False
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # 使用参数化查询来防止 SQL 注入
        cursor.execute(f"SELECT EXISTS(SELECT 1 FROM {table_name} WHERE id = ? LIMIT 1)", (item_id,))
        exists = cursor.fetchone()[0]
        conn.close()
        return bool(exists)
    except Exception as e:
        db_logger.error(f"在 {db_path} (表: {table_name}) 中检查 ID {item_id} 时出错: {e}", exc_info=True)
        return False

def add_id(db_path: str, item_id: str, item_type: str, table_name: str = 'history') -> None:
    """
    向指定表中添加一个新的 ID
    """
    if not item_id:
        return
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # 使用参数化查询
        cursor.execute(f"INSERT OR IGNORE INTO {table_name} (id, type) VALUES (?, ?)", (item_id, item_type))
        conn.commit()
        conn.close()
        db_logger.debug(f"ID {item_id} (类型: {item_type}) 已为数据库 {db_path} (表: {table_name}) 处理")
    except Exception as e:
        db_logger.error(f"向 {db_path} (表: {table_name}) 添加 ID {item_id} 失败: {e}", exc_info=True)

def get_all_ids(db_path: str, table_name: str = 'history') -> Set[str]:
    """
    获取指定表中的所有 ID 并返回一个集合
    """
    try:
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        # 使用 f-string 插入表名
        cursor.execute(f"SELECT id FROM {table_name}")
        # 使用集合推导式高效地将结果转为 set
        ids = {row[0] for row in cursor.fetchall()}
        conn.close()
        return ids
    except sqlite3.OperationalError as e:
        if "no such table" in str(e):
             db_logger.debug(f"表 {table_name} 在 {db_path} 中不存在，返回空集合")
             return set()
        db_logger.error(f"从 {db_path} (表: {table_name}) 获取所有 ID 失败: {e}", exc_info=True)
        return set()
    except Exception as e:
        db_logger.error(f"从 {db_path} (表: {table_name}) 获取所有 ID 失败: {e}", exc_info=True)
        return set()