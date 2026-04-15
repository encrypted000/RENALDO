from sshtunnel import SSHTunnelForwarder
import paramiko
import psycopg2
import os

def get_tunnel():
    tunnel = SSHTunnelForwarder(
        (os.environ["RADAR_SSH_HOST"], int(os.environ["RADAR_SSH_PORT"])),
        ssh_username=os.environ["RADAR_SSH_USER"],
        ssh_pkey=paramiko.RSAKey.from_private_key_file(os.environ["RADAR_SSH_KEY"]),
        remote_bind_address=("localhost", int(os.environ["RADAR_DB_PORT"])),
        local_bind_address=("localhost", 5433)
    )
    return tunnel

def get_connection():
    return psycopg2.connect(
        host="localhost",
        port=5433,
        dbname=os.environ["RADAR_DB_NAME"],
        user=os.environ["RADAR_DB_USER"],
        password=os.environ["RADAR_DB_PASS"]
    )