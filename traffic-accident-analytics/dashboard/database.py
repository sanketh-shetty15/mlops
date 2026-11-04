"""
dashboard/database.py
----------------------
PostgreSQL connection management for the Streamlit dashboard.

Uses connection pooling via a module-level singleton so that repeated
Streamlit reruns do not open a new connection on every interaction.

All queries go through get_connection() which handles:
  - Initial connection
  - Reconnection on stale connection
  - Clear error messages when the database is unavailable
"""

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg2
import psycopg2.extras
import pandas as pd
import streamlit as st

from config.config import get_db_connection_string, get_logger

logger = get_logger(__name__)

# ── Connection singleton ───────────────────────────────────────────────────────
# Stored in Streamlit session state so one connection is shared across
# all page interactions in a session.

def get_connection():
    """
    Return a live psycopg2 connection, reusing the session-state cache.
    Reconnects automatically if the connection has gone stale.
    """
    if "db_conn" not in st.session_state or st.session_state["db_conn"] is None:
        st.session_state["db_conn"] = _open_connection()

    conn = st.session_state["db_conn"]

    # Test if the connection is still alive
    try:
        conn.cursor().execute("SELECT 1")
    except Exception:
        logger.warning("Stale database connection detected — reconnecting.")
        try:
            conn.close()
        except Exception:
            pass
        conn = _open_connection()
        st.session_state["db_conn"] = conn

    return conn


def _open_connection():
    """Open a fresh psycopg2 connection. Shows a Streamlit error on failure."""
    try:
        conn = psycopg2.connect(get_db_connection_string())
        conn.set_session(readonly=True, autocommit=True)
        logger.info("Dashboard connected to PostgreSQL.")
        return conn
    except psycopg2.OperationalError as exc:
        st.error(
            f"**Cannot connect to PostgreSQL.**\n\n"
            f"Error: `{exc}`\n\n"
            "**Steps to fix:**\n"
            "1. Ensure PostgreSQL is running\n"
            "2. Check your `.env` credentials (POSTGRES_HOST, PORT, DB, USER, PASSWORD)\n"
            "3. Run the pipeline first: `python scripts/run_pipeline.py`"
        )
        st.stop()


def query_df(sql: str, params=None) -> pd.DataFrame:
    """
    Execute a SQL query and return the result as a pd.DataFrame.
    Uses SQLAlchemy engine for pandas compatibility (avoids DBAPI2 warning).
    """
    from sqlalchemy import create_engine, text
    from config.config import get_sqlalchemy_url

    # Use SQLAlchemy engine — pandas requires this from version 2.0+
    try:
        engine = create_engine(get_sqlalchemy_url())
        with engine.connect() as sa_conn:
            if params:
                return pd.read_sql_query(text(sql), sa_conn,
                                         params=params)
            else:
                return pd.read_sql_query(text(sql), sa_conn)
    except Exception as exc:
        # Fallback to psycopg2 direct query
        try:
            conn = get_connection()
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cols = [d[0] for d in cur.description]
                return pd.DataFrame(cur.fetchall(), columns=cols)
        except Exception as exc2:
            logger.error("Query failed: %s | SQL: %s", exc2, sql[:120])
            st.warning(f"Query error: {exc2}")
            return pd.DataFrame()


def query_scalar(sql: str, params=None, default=0):
    """
    Execute a query that returns a single scalar value.

    Returns *default* if the query fails or returns no rows.
    """
    conn = get_connection()
    try:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            result = cur.fetchone()
            return result[0] if result and result[0] is not None else default
    except Exception as exc:
        logger.error("Scalar query failed: %s | SQL: %s", exc, sql[:120])
        return default


def table_exists(table_name: str) -> bool:
    """Return True if a table exists in the public schema."""
    sql = """
        SELECT EXISTS (
            SELECT 1 FROM information_schema.tables
            WHERE table_schema = 'public'
            AND   table_name   = %s
        );
    """
    return bool(query_scalar(sql, params=(table_name,), default=False))


def get_available_years() -> list:
    """Return sorted list of years present in the analytics mart."""
    if not table_exists("accident_analytics_mart"):
        return []
    df = query_df(
        "SELECT DISTINCT year FROM accident_analytics_mart "
        "WHERE year IS NOT NULL ORDER BY year;"
    )
    return df["year"].tolist() if not df.empty else []
