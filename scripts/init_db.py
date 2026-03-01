#!/usr/bin/env python3
"""
Database initialization script for MemU PostgreSQL schema.

This script sets up the PostgreSQL database for MemU integration,
including the pgvector extension for vector storage and retrieval.

Usage:
    python scripts/init_db.py              # Initialize database
    python scripts/init_db.py --dry-run    # Show what would be done
    python scripts/init_db.py --verify     # Verify existing setup
    python scripts/init_db.py --help       # Show all options

Environment Variables:
    DATABASE_URL: PostgreSQL connection string (default: from .env or
                    postgresql://postgres:password@localhost:5432/memu)

Examples:
    # Initialize database with default settings
    python scripts/init_db.py

    # Check if database is properly set up
    python scripts/init_db.py --verify

    # Preview changes without applying them
    python scripts/init_db.py --dry-run
"""

import argparse
import re
import sys
from pathlib import Path

# Add project root to Python path for imports
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.shared.config import settings
from src.shared.logging import get_logger
from src.shared.errors import ConfigurationError, IntegrationError


logger = get_logger(__name__)


# SQL statements for database initialization
SQL_CREATE_PGVECTOR = """
CREATE EXTENSION IF NOT EXISTS vector;
"""

SQL_VERIFY_PGVECTOR = """
SELECT extname, extversion
FROM pg_extension
WHERE extname = 'vector';
"""

SQL_CHECK_CONNECTION = """
SELECT 1;
"""


async def connect_to_db(database_url: str | None = None):
    """
    Connect to PostgreSQL database.

    Args:
        database_url: PostgreSQL connection string. If None, uses settings.DATABASE_URL

    Returns:
        asyncpg connection object

    Raises:
        ConfigurationError: If DATABASE_URL is not set
        IntegrationError: If connection fails
    """
    try:
        import asyncpg
    except ImportError:
        raise ConfigurationError(
            "asyncpg is required for database initialization. "
            "Install it with: pip install asyncpg"
        )

    url = database_url or settings.DATABASE_URL

    if not url or url == "postgresql://postgres:password@localhost:5432/memu":
        logger.warning(
            "Using default DATABASE_URL. Set DATABASE_URL environment variable "
            "or update .env file with your PostgreSQL connection string."
        )

    logger.info("Connecting to PostgreSQL database", extra={"database_url": _mask_password(url)})

    try:
        conn = await asyncpg.connect(url)
        logger.info("Successfully connected to database")
        return conn
    except Exception as e:
        raise IntegrationError(
            f"Failed to connect to database: {e}",
            details={"database_url": _mask_password(url)}
        )


def _mask_password(url: str) -> str:
    """
    Mask password in database URL for logging.

    Handles URLs with special characters in passwords and various formats.

    Args:
        url: Database connection string

    Returns:
        URL with password masked

    Examples:
        >>> _mask_password("postgresql://user:pass@localhost:5432/db")
        'postgresql://user:****@localhost:5432/db'
        >>> _mask_password("postgresql://user@localhost:5432/db")
        'postgresql://user@localhost:5432/db'
    """
    # Check if URL has both protocol and auth section
    if "://" not in url or "@" not in url:
        return url

    # Split protocol from the rest
    protocol, rest = url.split("://", 1)

    # Find the last @ to separate auth from host (handles @ in passwords)
    at_pos = rest.rfind("@")
    if at_pos == -1:
        return url

    auth = rest[:at_pos]
    host = rest[at_pos + 1:]

    # Check if auth contains a password (has :)
    if ":" not in auth:
        # No password, return URL as is
        return url

    # Split user and password (only on first : to handle : in passwords)
    user, _ = auth.split(":", 1)

    # Reconstruct URL with masked password
    return f"{protocol}://{user}:****@{host}"


async def verify_connection(conn) -> bool:
    """
    Verify database connection is working.

    Args:
        conn: asyncpg connection object

    Returns:
        True if connection is working
    """
    try:
        result = await conn.fetchval(SQL_CHECK_CONNECTION)
        if result == 1:
            logger.info("Database connection verified")
            return True
        return False
    except Exception as e:
        logger.error("Connection verification failed", extra={"error": str(e)})
        return False


async def check_pgvector_extension(conn) -> dict[str, str | None]:
    """
    Check if pgvector extension is installed.

    Args:
        conn: asyncpg connection object

    Returns:
        Dictionary with extension status (extname, extversion)
    """
    try:
        row = await conn.fetchrow(SQL_VERIFY_PGVECTOR)
        if row:
            result = {
                "extname": row["extname"],
                "extversion": row["extversion"]
            }
            logger.info(
                "pgvector extension found",
                extra={"version": row["extversion"]}
            )
            return result
        else:
            logger.info("pgvector extension not installed")
            return {"extname": None, "extversion": None}
    except Exception as e:
        logger.error("Failed to check pgvector extension", extra={"error": str(e)})
        return {"extname": None, "extversion": None}


async def create_pgvector_extension(conn, dry_run: bool = False) -> bool:
    """
    Create pgvector extension in the database.

    Args:
        conn: asyncpg connection object
        dry_run: If True, only show what would be done

    Returns:
        True if extension was created or already exists
    """
    if dry_run:
        logger.info("[DRY RUN] Would execute: CREATE EXTENSION IF NOT EXISTS vector;")
        return True

    try:
        # Check if extension already exists
        status = await check_pgvector_extension(conn)

        if status["extname"] == "vector":
            logger.info("pgvector extension already exists, skipping creation")
            return True

        # Create the extension
        await conn.execute(SQL_CREATE_PGVECTOR)
        logger.info("Successfully created pgvector extension")

        # Verify it was created
        new_status = await check_pgvector_extension(conn)
        if new_status["extname"] == "vector":
            logger.info(
                "pgvector extension verified",
                extra={"version": new_status["extversion"]}
            )
            return True
        else:
            logger.error("Extension creation appeared to succeed but verification failed")
            return False

    except Exception as e:
        logger.error("Failed to create pgvector extension", extra={"error": str(e)})
        raise IntegrationError(
            f"Failed to create pgvector extension: {e}",
            details={"extension": "vector"}
        )


async def verify_database_setup(database_url: str | None = None) -> dict:
    """
    Verify the database is properly set up for MemU.

    Args:
        database_url: Optional database connection string

    Returns:
        Dictionary with verification results
    """
    conn = None
    try:
        conn = await connect_to_db(database_url)

        results = {
            "connected": await verify_connection(conn),
            "pgvector_installed": False,
            "pgvector_version": None
        }

        pgvector_status = await check_pgvector_extension(conn)
        results["pgvector_installed"] = pgvector_status["extname"] == "vector"
        results["pgvector_version"] = pgvector_status["extversion"]

        return results

    finally:
        if conn:
            await conn.close()


async def initialize_database(
    database_url: str | None = None,
    dry_run: bool = False,
    verify_only: bool = False
) -> bool:
    """
    Initialize the MemU database schema.

    Args:
        database_url: Optional database connection string
        dry_run: If True, only show what would be done
        verify_only: If True, only verify existing setup

    Returns:
        True if initialization succeeded
    """
    conn = None
    try:
        if verify_only:
            logger.info("Verifying database setup...")
            results = await verify_database_setup(database_url)

            logger.info("=" * 60)
            logger.info("Database Verification Results:")
            logger.info("=" * 60)
            logger.info(f"Connected:           {results['connected']}")
            logger.info(f"pgvector Installed:  {results['pgvector_installed']}")
            if results['pgvector_version']:
                logger.info(f"pgvector Version:    {results['pgvector_version']}")
            logger.info("=" * 60)

            if results["connected"] and results["pgvector_installed"]:
                logger.info("✓ Database is properly configured for MemU")
                return True
            else:
                logger.error("✗ Database is not properly configured")
                if not results["connected"]:
                    logger.error("  - Cannot connect to database")
                if not results["pgvector_installed"]:
                    logger.error("  - pgvector extension is not installed")
                    logger.error("  - Run: python scripts/init_db.py")
                return False

        if dry_run:
            logger.info("=" * 60)
            logger.info("DRY RUN MODE - No changes will be made")
            logger.info("=" * 60)

        conn = await connect_to_db(database_url)

        # Verify connection
        if not await verify_connection(conn):
            raise IntegrationError("Database connection verification failed")

        # Create pgvector extension
        logger.info("Setting up pgvector extension...")
        if not await create_pgvector_extension(conn, dry_run=dry_run):
            raise IntegrationError("Failed to set up pgvector extension")

        if dry_run:
            logger.info("=" * 60)
            logger.info("DRY RUN complete - No changes were made")
            logger.info("Run without --dry-run to apply these changes")
            logger.info("=" * 60)
        else:
            logger.info("=" * 60)
            logger.info("Database initialization complete!")
            logger.info("=" * 60)
            logger.info("MemU can now use PostgreSQL for persistent storage.")
            logger.info("Note: The MemU SDK will create additional tables on first use.")

        return True

    except ConfigurationError as e:
        logger.error("Configuration error", extra={"error": str(e)})
        return False
    except IntegrationError as e:
        logger.error("Integration error", extra={"error": str(e)})
        return False
    except Exception as e:
        logger.exception("Unexpected error during database initialization")
        return False
    finally:
        if conn:
            await conn.close()


def parse_arguments() -> argparse.Namespace:
    """
    Parse command line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Initialize MemU PostgreSQL database with pgvector extension",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s                  Initialize database with default settings
  %(prog)s --verify         Check if database is properly set up
  %(prog)s --dry-run        Preview changes without applying them
  %(prog)s --database-url postgresql://user:pass@host:5432/db
                            Use custom database connection string

Environment Variables:
  DATABASE_URL              PostgreSQL connection string (overrides default)
        """
    )

    parser.add_argument(
        "--database-url", "-d",
        type=str,
        default=None,
        help="PostgreSQL connection string (default: DATABASE_URL env var or "
             "postgresql://postgres:password@localhost:5432/memu)"
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Show what would be done without making changes"
    )

    parser.add_argument(
        "--verify", "-v",
        action="store_true",
        help="Verify existing database setup without making changes"
    )

    return parser.parse_args()


async def main() -> int:
    """
    Main entry point for database initialization script.

    Returns:
        Exit code (0 for success, 1 for failure)
    """
    args = parse_arguments()

    if args.verify:
        logger.info("Running in verification mode...")
        success = await initialize_database(
            database_url=args.database_url,
            verify_only=True
        )
    else:
        success = await initialize_database(
            database_url=args.database_url,
            dry_run=args.dry_run
        )

    return 0 if success else 1


if __name__ == "__main__":
    import asyncio
    sys.exit(asyncio.run(main()))
