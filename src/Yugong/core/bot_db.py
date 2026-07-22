"""
这个是用来存储模板信息，防止反复请求的。暂时用不到
"""

import json
import sqlite3
from datetime import datetime
from pathlib import Path

from src.Yugong.core.logger import BotLogger
from src.Yugong.utilities.path_helper import PROJECT_ROOT


class BotDB:
    """
    Wiki机器人数据库管理类

    使用SQLite单文件数据库，支持高性能读写（WAL模式）。
    提供通用的增删改查方法，自动处理JSON序列化和中文字符。

    数据库表结构：
        1. template - Wiki模板信息
           - name (TEXT, 主键): 模板名称
           - aliases (TEXT, JSON数组): 所有别名/重定向列表
           - type (TEXT): 模板类型（如navbox/infobox）
           - purpose (TEXT, 可选): 用途描述
           - usage (TEXT, 可选): 用法说明
           - scope (TEXT, 可选): 使用范围

        2. alias - 重定向映射
           - id (INTEGER, 主键, 自增): 唯一标识
           - namespace (TEXT): 命名空间（如Template/User）
           - title (TEXT): 标题（不含命名空间）
           - target_table (TEXT): 目标表名
           - target_key (TEXT): 目标表的键值
           - 唯一约束: (namespace, title)

        3. talks - 讨论记录
           - id (INTEGER, 主键, 自增): 唯一标识
           - section_title (TEXT): 段落标题
           - page (TEXT): 所在页面
           - start_time (TEXT, 可选): 开始时间（ISO 8601 格式）
           - end_time (TEXT, 可选): 结束时间（ISO 8601 格式）
           - last_reply_time (TEXT, 可选): 最后回复时间（ISO 8601 格式）
           - participants (TEXT, 可选): 参与者列表（JSON数组）
           - is_closed (INTEGER): 是否结束（0=未结束, 1=已结束）

        4. preferences - 用户偏好设置
           - username (TEXT, 主键): 用户名
           - settings (TEXT, JSON对象): 设置内容字典
    """

    def __init__(self, db_path: Path | None = None):
        """
        初始化数据库连接

        Args:
            db_path: 数据库文件路径，默认为 PROJECT_ROOT/data/db/db.sqlite3
        """
        if db_path is None:
            db_path = PROJECT_ROOT / "data" / "db" / "db.sqlite3"

        self.db_path = db_path
        self.logger = BotLogger("bot_db")

        db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_database()

    def _get_connection(self) -> sqlite3.Connection:
        """
        获取数据库连接（启用WAL模式和外键约束）

        Returns:
            sqlite3.Connection: 数据库连接对象
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def _init_database(self):
        """创建所有数据表（如果不存在）"""
        with self._get_connection() as conn:
            cursor = conn.cursor()

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS template (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    target TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS alias (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    target TEXT NOT NULL
                )
            """)

            cursor.execute("""
                CREATE TABLE IF NOT EXISTS category (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    target TEXT NOT NULL
                )
            """)

            conn.commit()
            # self._migrate_talks_table(conn)
            self.logger.info("数据库初始化完成")

    def insert(self, table: str, data: dict[str, any]) -> bool:
        """
        插入数据到指定表

        Args:
            table: 表名
            data: 要插入的数据字典

        Returns:
            bool: 插入是否成功
        """
        try:
            with self._get_connection() as conn:
                columns = ", ".join(data.keys())
                placeholders = ", ".join(["?"] * len(data))
                values = [self._serialize_value(v) for v in data.values()]

                query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
                conn.execute(query, values)
                conn.commit()
                self.logger.debug(f"插入数据到 {table}: {data}")
                return True
        except Exception as e:
            self.logger.error(f"插入数据失败: {e}")
            return False

    def update(self, table: str, data: dict[str, any], conditions: dict[str, any]) -> bool:
        """
        更新指定表的数据

        Args:
            table: 表名
            data: 要更新的字段和值
            conditions: 更新条件（多个条件用AND连接）

        Returns:
            bool: 更新是否成功
        """
        try:
            with self._get_connection() as conn:
                set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
                where_clause = " AND ".join([f"{k} = ?" for k in conditions.keys()])

                values = [self._serialize_value(v) for v in data.values()]
                values += [self._serialize_value(v) for v in conditions.values()]

                query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
                cursor = conn.execute(query, values)
                conn.commit()

                if cursor.rowcount > 0:
                    self.logger.debug(f"更新 {table} 数据: {data}, 条件: {conditions}")
                    return True
                else:
                    self.logger.warning(f"未找到匹配的记录进行更新")
                    return False
        except Exception as e:
            self.logger.error(f"更新数据失败: {e}")
            return False

    def delete(self, table: str, conditions: dict[str, any]) -> bool:
        """
        从指定表删除数据

        Args:
            table: 表名
            conditions: 删除条件（多个条件用AND连接）

        Returns:
            bool: 删除是否成功
        """
        try:
            with self._get_connection() as conn:
                where_clause = " AND ".join([f"{k} = ?" for k in conditions.keys()])
                values = [self._serialize_value(v) for v in conditions.values()]

                query = f"DELETE FROM {table} WHERE {where_clause}"
                cursor = conn.execute(query, values)
                conn.commit()

                if cursor.rowcount > 0:
                    self.logger.debug(f"从 {table} 删除数据, 条件: {conditions}")
                    return True
                else:
                    self.logger.warning(f"未找到匹配的记录进行删除")
                    return False
        except Exception as e:
            self.logger.error(f"删除数据失败: {e}")
            return False

    def search(self, table: str, conditions: dict[str, any] | None = None,
               columns: list[str] | None = None, limit: int | None = None) -> list[dict[str, any]]:
        """
        搜索指定表的数据（精确匹配）

        Args:
            table: 表名
            conditions: 搜索条件字典（多条件AND连接），None表示无条件
            columns: 要查询的列名列表，None表示查询所有列
            limit: 限制返回结果数量

        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        try:
            with self._get_connection() as conn:
                select_columns = ", ".join(columns) if columns else "*"
                query = f"SELECT {select_columns} FROM {table}"
                values = []

                if conditions:
                    where_clause = " AND ".join([f"{k} = ?" for k in conditions.keys()])
                    query += f" WHERE {where_clause}"
                    values = [self._serialize_value(v) for v in conditions.values()]

                if limit:
                    query += f" LIMIT {limit}"

                cursor = conn.execute(query, values)
                rows = cursor.fetchall()

                results = [dict(row) for row in rows]
                results = [self._deserialize_row(row) for row in results]

                self.logger.debug(f"搜索 {table}, 条件: {conditions}, 结果数: {len(results)}")
                return results
        except Exception as e:
            self.logger.error(f"搜索数据失败: {e}")
            return []

    def search_like(self, table: str, conditions: dict[str, str] | None = None,
                    columns: list[str] | None = None, limit: int | None = None) -> list[dict[str, any]]:
        """
        模糊搜索指定表的数据（LIKE匹配）

        Args:
            table: 表名
            conditions: 模糊搜索条件字典（多条件AND连接），值会自动添加%通配符
            columns: 要查询的列名列表，None表示查询所有列
            limit: 限制返回结果数量

        Returns:
            List[Dict[str, Any]]: 搜索结果列表
        """
        try:
            with self._get_connection() as conn:
                select_columns = ", ".join(columns) if columns else "*"
                query = f"SELECT {select_columns} FROM {table}"
                values = []

                if conditions:
                    where_clause = " AND ".join([f"{k} LIKE ?" for k in conditions.keys()])
                    query += f" WHERE {where_clause}"
                    values = [f"%{v}%" for v in conditions.values()]

                if limit:
                    query += f" LIMIT {limit}"

                cursor = conn.execute(query, values)
                rows = cursor.fetchall()

                results = [dict(row) for row in rows]
                results = [self._deserialize_row(row) for row in results]

                self.logger.debug(f"模糊搜索 {table}, 条件: {conditions}, 结果数: {len(results)}")
                return results
        except Exception as e:
            self.logger.error(f"模糊搜索数据失败: {e}")
            return []

    def search_query(self, table: str, where_clause: str = "",
                     values: list[any] | None = None,
                     columns: list[str] | None = None,
                     limit: int | None = None) -> list[dict[str, any]]:
        """
        通用查询：支持自定义 WHERE 子句（可包含 <、>、LIKE 等任意运算符）。

        Args:
            table: 表名
            where_clause: WHERE 后的条件子句（不含 "WHERE" 关键字），
                          如 ``"start_time > ? AND page = ?"``。
                          为空则查询全部记录。
            values: 与占位符 ``?`` 一一对应的参数列表
            columns: 要查询的列名列表，None 表示查询所有列
            limit: 限制返回结果数量

        Returns:
            List[Dict[str, Any]]: 查询结果列表
        """
        try:
            with self._get_connection() as conn:
                select_columns = ", ".join(columns) if columns else "*"
                query = f"SELECT {select_columns} FROM {table}"
                if where_clause:
                    query += f" WHERE {where_clause}"
                if limit is not None:
                    query += f" LIMIT {limit}"

                params = [self._serialize_value(v) for v in (values or [])]
                cursor = conn.execute(query, params)
                rows = cursor.fetchall()

                results = [dict(row) for row in rows]
                results = [self._deserialize_row(row) for row in results]

                self.logger.debug(
                    f"通用查询 {table}, WHERE {where_clause!r}, "
                    f"结果数: {len(results)}"
                )
                return results
        except Exception as e:
            self.logger.error(f"通用查询失败: {e}")
            return []

    def execute_transaction(self, operations: list[tuple[str, list[any]]]) -> bool:
        """
        执行事务（多条SQL操作）

        Args:
            operations: 操作列表，每个元素为 (sql_query, params) 元组

        Returns:
            bool: 事务是否成功执行
        """
        try:
            with self._get_connection() as conn:
                for query, params in operations:
                    serialized_params = [self._serialize_value(p) for p in params]
                    conn.execute(query, serialized_params)
                conn.commit()
                self.logger.debug(f"执行事务成功, 操作数: {len(operations)}")
                return True
        except Exception as e:
            self.logger.error(f"执行事务失败: {e}")
            return False

    @staticmethod
    def _serialize_value(value: any) -> any:
        """
        序列化值为适合存储的格式（list/dict转为JSON字符串，datetime转为ISO 8601）

        Args:
            value: 要序列化的值

        Returns:
            序列化后的值
        """
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, (list, dict)):
            return json.dumps(value, ensure_ascii=False)
        return value

    @staticmethod
    def _deserialize_row(row: dict[str, any]) -> dict[str, any]:
        """
        反序列化行数据（JSON字符串转回list/dict）

        Args:
            row: 数据库行数据字典

        Returns:
            反序列化后的行数据
        """
        deserialized = {}
        for key, value in row.items():
            if isinstance(value, str):
                try:
                    deserialized[key] = json.loads(value)
                except (json.JSONDecodeError, TypeError):
                    deserialized[key] = value
            else:
                deserialized[key] = value
        return deserialized

    def execute_raw(self, sql: str, params: list[any] | None = None) -> list[dict[str, any]]:
        """
        执行原始SQL查询并返回结果

        Args:
            sql: SQL查询语句
            params: 参数列表

        Returns:
            List[Dict[str, Any]]: 查询结果
        """
        try:
            with self._get_connection() as conn:
                cursor = conn.execute(sql, params or [])
                rows = cursor.fetchall()
                results = [dict(row) for row in rows]
                results = [self._deserialize_row(row) for row in results]
                return results
        except Exception as e:
            self.logger.error(f"执行原始SQL失败: {e}")
            return []

bot_db = BotDB()
