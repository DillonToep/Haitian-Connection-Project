import queue
import threading

import pyodbc

from .config import SQL_CONNECTION_STRING, SQL_POOL_SIZE

_CONNECT_TIMEOUT = 5

# Bounds how many physical connections ever exist at once. get_connection()
# blocks (briefly) if every connection is already checked out, instead of
# opening an unbounded number of new ones under load -- same idea as a
# typical DB connection pool.
_semaphore = threading.Semaphore(SQL_POOL_SIZE)
_pool: "queue.Queue[pyodbc.Connection]" = queue.Queue(maxsize=SQL_POOL_SIZE)


def _create_raw_connection() -> pyodbc.Connection:
    return pyodbc.connect(SQL_CONNECTION_STRING, timeout=_CONNECT_TIMEOUT)


class PooledConnection:
    """Wraps a real pyodbc connection so existing call sites --
    `with closing(get_connection()) as connection:` -- keep working
    unchanged. Calling .close() returns the underlying connection to the
    pool instead of closing the socket, unless the connection turned out
    to be broken (e.g. SQL Server dropped an idle connection), in which
    case it's discarded and replaced so a bad connection never gets
    handed to the next request."""

    __slots__ = ("_conn", "_broken")

    def __init__(self, conn: pyodbc.Connection):
        self._conn = conn
        self._broken = False

    def cursor(self):
        try:
            return self._conn.cursor()
        except pyodbc.Error:
            self._broken = True
            raise

    def commit(self):
        try:
            self._conn.commit()
        except pyodbc.Error:
            self._broken = True
            raise

    def rollback(self):
        try:
            self._conn.rollback()
        except pyodbc.Error:
            self._broken = True
            raise

    def close(self):
        conn, broken = self._conn, self._broken
        self._conn = None  # guard against accidental reuse after close()

        if broken:
            try:
                conn.close()
            except pyodbc.Error:
                pass
            try:
                conn = _create_raw_connection()
            except pyodbc.Error:
                # DB unreachable right now -- release the pool slot without
                # putting anything back; a later get_connection() will try
                # to open a fresh one itself.
                _semaphore.release()
                return

        try:
            _pool.put_nowait(conn)
        except queue.Full:
            # Shouldn't happen given the semaphore, but don't leak a
            # connection if it does.
            try:
                conn.close()
            except pyodbc.Error:
                pass
        _semaphore.release()


def get_connection() -> PooledConnection:
    _semaphore.acquire()
    try:
        conn = _pool.get_nowait()
    except queue.Empty:
        try:
            conn = _create_raw_connection()
        except pyodbc.Error:
            _semaphore.release()
            raise

    # Idle pooled connections can be dropped by SQL Server or a firewall
    # while sitting unused -- one cheap round trip catches that before
    # handing a dead connection to a route handler.
    try:
        conn.cursor().execute("SELECT 1")
    except pyodbc.Error:
        try:
            conn.close()
        except pyodbc.Error:
            pass
        try:
            conn = _create_raw_connection()
        except pyodbc.Error:
            _semaphore.release()
            raise

    return PooledConnection(conn)


def row_to_dict(cursor, row):
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))