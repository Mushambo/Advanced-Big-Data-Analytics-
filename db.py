"""Shared database connection helper. Connection settings come from environment
variables so that no password is stored in the repository."""
import os

import psycopg2


def connect(autocommit: bool = False):
    conn = psycopg2.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "iot_assignment"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD"),
    )
    conn.autocommit = autocommit
    return conn
