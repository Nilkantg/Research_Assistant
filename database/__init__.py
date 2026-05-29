# database/__init__.py
#
# Exposes the public API of the database package.
#
# Other modules import like this:
#   from database import ChatSession, ChatMessage, get_sync_db
#
# Instead of the verbose:
#   from database.models import ChatSession, ChatMessage
#   from database.session import get_sync_db

from .models import Base, ChatSession, ChatMessage
from .session import (
    init_database,
    get_sync_db,
    get_async_db,
    get_db_dependency,
    sync_engine,
    async_engine,
)

__all__ = [
    # SQLAlchemy base — needed if you run Alembic migrations
    "Base",
    # Table models
    "ChatSession",
    "ChatMessage",
    # Database lifecycle
    "init_database",
    # Session context managers
    "get_sync_db",       # use in sync code / startup scripts
    "get_async_db",      # use in async utility code
    "get_db_dependency", # use in FastAPI route Depends()
    # Engines — exposed for advanced use (e.g. Alembic, testing)
    "sync_engine",
    "async_engine",
]