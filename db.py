import os
import psycopg2
from psycopg2 import pool, extensions
from psycopg2.extras import RealDictCursor

DB_CONFIG = {
    "host":     os.environ.get("PG_HOST", "192.168.88.24"),
    "port":     os.environ.get("PG_PORT", "5432"),
    "dbname":   os.environ.get("PG_DBNAME", "garindra"),
    "user":     os.environ.get("PG_USER", "production_user"),
    "password": os.environ.get("PG_PASSWORD", "372026production_"),
    "options":  "-c search_path=production,public -c statement_timeout=30000",
}

# Sesuaikan maxconn dengan jumlah checker/PC yang connect bersamaan.
_pool = pool.ThreadedConnectionPool(minconn=7, maxconn=40, **DB_CONFIG)


def get_conn():

    return _pool.getconn()


def release_conn(conn):
    try:
        status = conn.get_transaction_status()
        if status != extensions.TRANSACTION_STATUS_IDLE:
            conn.rollback()
    except Exception:
        pass
    _pool.putconn(conn)


def dict_cursor(conn):
    return conn.cursor(cursor_factory=RealDictCursor)

def close_pool():
    _pool.closeall()
