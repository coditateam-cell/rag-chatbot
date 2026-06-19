import os
import sys
import time
import asyncio
import logging
from sqlalchemy import text

logger = logging.getLogger(__name__)

async def check_postgres() -> bool:
    """Check PostgreSQL database connectivity."""
    try:
        from app.db.connection import engine
        # Execute a simple query to verify connection
        async with engine.begin() as conn:
            await conn.execute(text("SELECT 1"))
        return True
    except Exception as e:
        logger.debug("PostgreSQL health check failed: %s", e)
        return False

def check_qdrant() -> bool:
    """Check Qdrant vector database connectivity."""
    try:
        from qdrant_client import QdrantClient
        host = os.getenv("QDRANT_HOST", "qdrant")
        port = int(os.getenv("QDRANT_PORT", "6333"))
        client = QdrantClient(host=host, port=port, timeout=2.0)
        # Call get_collections to verify connection
        client.get_collections()
        return True
    except Exception as e:
        logger.debug("Qdrant health check failed: %s", e)
        return False

def check_minio() -> bool:
    """Check MinIO object storage connectivity."""
    try:
        from minio import Minio
        endpoint = os.getenv("MINIO_ENDPOINT")
        if endpoint:
            host_port = endpoint
        else:
            host = os.getenv("MINIO_HOST", "minio")
            port = os.getenv("MINIO_PORT", "9000")
            host_port = f"{host}:{port}"
        
        access_key = os.getenv("MINIO_ROOT_USER", "minioadmin")
        secret_key = os.getenv("MINIO_ROOT_PASSWORD", "minioadmin123")
        
        client = Minio(
            host_port,
            access_key=access_key,
            secret_key=secret_key,
            secure=False,
        )
        # Verify connection using a lightweight check
        client.bucket_exists("healthcheck-probe-bucket")
        return True
    except Exception as e:
        logger.debug("MinIO health check failed: %s", e)
        return False

async def wait_for_services(timeout: float = 60.0, interval: float = 2.0, include_minio: bool = True) -> None:
    """Wait for PostgreSQL, Qdrant (and optionally MinIO) to be healthy. Exits on timeout."""
    if "pytest" in sys.modules or os.getenv("TESTING") == "true":
        logger.info("Running in test environment. Skipping startup validation checks.")
        return

    use_local = os.getenv("USE_LOCAL_MODE", "false").lower() == "true"
    if use_local:
        logger.info("Running in LOCAL MODE. Skipping external Qdrant and MinIO validation checks.")
        # Verify local SQLite database is responsive
        postgres_ok = await check_postgres()
        if postgres_ok:
            logger.info("Local database verified successfully.")
            return
        else:
            logger.error("Local database health check failed.")
            sys.exit(1)

    logger.info("Starting backend services health check and startup validation...")
    start_time = time.time()
    
    while time.time() - start_time < timeout:
        postgres_ok = await check_postgres()
        qdrant_ok = check_qdrant()
        minio_ok = check_minio() if include_minio else True
        
        if postgres_ok and qdrant_ok and minio_ok:
            logger.info("All dependent services are healthy.")
            return
            
        unhealthy = []
        if not postgres_ok:
            unhealthy.append("PostgreSQL")
        if not qdrant_ok:
            unhealthy.append("Qdrant")
        if include_minio and not minio_ok:
            unhealthy.append("MinIO")
            
        logger.info(
            "Waiting for services: %s. Retrying in %s seconds...",
            ", ".join(unhealthy),
            interval
        )
        await asyncio.sleep(interval)
        
    logger.error("Startup validation failed: Dependent services not healthy within 60 seconds.")
    sys.exit(1)

