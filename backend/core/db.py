from contextlib import contextmanager

from sqlalchemy import MetaData, create_engine
from sqlalchemy.pool import StaticPool

from core.config import DATABASE_URL

metadata = MetaData()

if DATABASE_URL.startswith('sqlite'):
    # 便于在本机/CI 用 SQLite 跑业务核验；文件库关闭同线程限制，内存库共用一条连接。
    memory = ':memory:' in DATABASE_URL or DATABASE_URL in ('sqlite://', 'sqlite+pysqlite://')
    engine = create_engine(
        DATABASE_URL,
        connect_args={'check_same_thread': False, 'timeout': 30},
        poolclass=StaticPool if memory else None,
        pool_pre_ping=True,
    )
else:
    engine = create_engine(DATABASE_URL, pool_pre_ping=True)

@contextmanager
def transaction():
    with engine.begin() as conn:
        yield conn
