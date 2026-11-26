"""极简幂等补列：metadata.create_all 只建新表，不会给旧表加列。

演示/评测若复用了旧的数据卷，启动时按模型定义补齐缺失列；全新库上全部为空操作。
"""
import logging

from sqlalchemy import inspect, text
from sqlalchemy.schema import CreateColumn

from core.db import metadata

log = logging.getLogger('uvicorn.error')


def ensure_columns(engine):
    metadata.create_all(engine)
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    dialect = engine.dialect
    for table in metadata.sorted_tables:
        if table.name not in existing_tables:
            continue
        present = {column['name'] for column in inspector.get_columns(table.name)}
        for column in table.columns:
            if column.name in present:
                continue
            column_ddl = str(CreateColumn(column).compile(dialect=dialect)).strip()
            statement = f'ALTER TABLE {table.name} ADD COLUMN {column_ddl}'
            try:
                with engine.begin() as conn:
                    conn.execute(text(statement))
                log.info('schema patched: %s + %s', table.name, column.name)
            except Exception:
                log.exception('could not apply: %s', statement)
    return True
