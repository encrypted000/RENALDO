"""
test_connection.py
-------------------
Tests the SSH tunnel and PostgreSQL connection.
Run with: python -m pytest tests/test_connection.py -v
Note: requires environment variables to be set.
"""

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
import pandas as pd


def test_env_variables_set():
    """All required environment variables must be set."""
    required = [
        "RADAR_SSH_HOST",
        "RADAR_SSH_PORT",
        "RADAR_SSH_USER",
        "RADAR_SSH_KEY",
        "RADAR_DB_HOST",
        "RADAR_DB_PORT",
        "RADAR_DB_NAME",
        "RADAR_DB_USER",
    ]
    missing = [k for k in required if not os.environ.get(k)]
    assert not missing, f"Missing environment variables: {missing}"


def test_ssh_key_file_exists():
    """SSH key file must exist at the specified path."""
    key_path = os.environ.get("RADAR_SSH_KEY", "")
    assert os.path.exists(key_path), f"SSH key not found: {key_path}"


def test_database_connection():
    """Full end-to-end connection test through SSH tunnel."""
    from config.settings import get_tunnel, get_connection

    tunnel = get_tunnel()
    tunnel.start()

    try:
        conn = get_connection()
        result = pd.read_sql("SELECT 1 AS test", conn)
        assert result["test"][0] == 1, "Database query returned unexpected result"
        conn.close()
    finally:
        tunnel.stop()


def test_patient_demographics_table_exists():
    """patient_demographics table must exist and be readable."""
    from config.settings import get_tunnel, get_connection

    tunnel = get_tunnel()
    tunnel.start()

    try:
        conn = get_connection()
        result = pd.read_sql(
            "SELECT COUNT(*) AS cnt FROM patient_demographics LIMIT 1",
            conn
        )
        assert result["cnt"][0] >= 0
        conn.close()
    finally:
        tunnel.stop()
