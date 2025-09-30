import time
import psycopg2
from psycopg2 import OperationalError
from database import engine, Base
from models import User, Document, DocumentChunk
import os

def wait_for_db():
    """Wait for database to be ready"""
    db_url = os.getenv("DATABASE_URL", "postgresql://postgres:password@db:5432/knowledge_api")

    # Extract connection params from URL
    # postgresql://postgres:password@db:5432/knowledge_api
    parts = db_url.replace("postgresql://", "").split("/")
    db_name = parts[1]
    user_pass_host = parts[0].split("@")
    user_pass = user_pass_host[0].split(":")
    host_port = user_pass_host[1].split(":")

    user = user_pass[0]
    password = user_pass[1]
    host = host_port[0]
    port = host_port[1]

    max_retries = 30
    retry_interval = 2

    for i in range(max_retries):
        try:
            conn = psycopg2.connect(
                host=host,
                port=port,
                user=user,
                password=password,
                database=db_name
            )
            conn.close()
            print("Database is ready!")
            return True
        except OperationalError:
            print(f"Database not ready, retrying... ({i+1}/{max_retries})")
            time.sleep(retry_interval)

    print("Database failed to become ready")
    return False

def create_tables():
    print("Creating database tables...")
    Base.metadata.create_all(bind=engine)
    print("Tables created successfully!")

if __name__ == "__main__":
    if wait_for_db():
        create_tables()
    else:
        exit(1)