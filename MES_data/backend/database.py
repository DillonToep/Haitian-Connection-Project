import pyodbc

from .config import SQL_CONNECTION_STRING


def get_connection():
    return pyodbc.connect(SQL_CONNECTION_STRING, timeout=5)


def row_to_dict(cursor, row):
    columns = [column[0] for column in cursor.description]
    return dict(zip(columns, row))
