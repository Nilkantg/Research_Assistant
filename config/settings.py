# config/settings.py
#
# WHY THIS FILE EXISTS:
# This is the single source of truth for all configuration in the app.
# Every setting lives here. No other file hardcodes values.
#
# HOW IT WORKS:
# Pydantic's BaseSettings reads from environment variables automatically.
# The class field name maps to the env var name (case-insensitive).
# Example: OPENAI_API_KEY in your .env -> settings.openai_api_key in Python.

from pydantic_settings import BaseSettings
from pydantic import Field, validator
from functools import lru_cache
from pathlib import Path


class Settings(BaseSettings):
    """
    Application settings loaded from environment variables.

    Pydantic BaseSettings automatically reads from:
    1. The actual environment (os.environ)
    2. A .env file in the current directory (if python-dotenv is installed)

    Fields with no default MUST be set via environment variable.
    Fields with defaults can be overridden via environment variable.
    """

    # ---------------------------------------------------------------
    # LLM Provider Settings
    # ---------------------------------------------------------------

    # No default — this MUST be set. If missing, app fails at startup
    # with a clear error: "openai_api_key field required"
    openai_api_key: str = Field(..., description="OpenAI API key")

    openai_chat_model: str = Field(
        default="gpt-4o-mini",
        description="Chat model to use for responses"
    )

    openai_embedding_model: str = Field(
        default="text-embedding-3-small",
        description="Embedding model for document vectorization"
    )

    # ---------------------------------------------------------------
    # Application Settings
    # ---------------------------------------------------------------

    app_env: str = Field(
        default="development",
        description="Environment: development | staging | production"
    )

    app_host: str = Field(default="0.0.0.0")
    app_port: int = Field(default=8000)

    secret_key: str = Field(
        default="dev-secret-key-change-in-production",
        description="Secret key for session token signing"
    )

    # ---------------------------------------------------------------
    # Vector Store Settings
    # ---------------------------------------------------------------

    chroma_persist_dir: str = Field(
        default="./data/chroma_db",
        description="Directory where ChromaDB stores its data"
    )

    chroma_collection_name: str = Field(
        default="research_documents",
        description="ChromaDB collection name"
    )

    # ---------------------------------------------------------------
    # Database Settings
    # ---------------------------------------------------------------

    database_url: str = Field(
        default="sqlite:///./data/chat_history.db",
        description="Database connection string for chat history"
    )

    # ---------------------------------------------------------------
    # RAG Pipeline Settings
    # ---------------------------------------------------------------

    # How many chunks to retrieve from vector store per query.
    # Real-world tuning:
    #   Too low (1-2): misses relevant context, poor answers
    #   Too high (10+): noisy context, wastes tokens, slower responses
    #   4-6 is usually the sweet spot
    retrieval_top_k: int = Field(
        default=5,
        description="Number of chunks to retrieve per query"
    )

    # Chunk size in characters (approximate).
    # For research papers: 500-800 (dense, technical content)
    # For general docs: 300-500
    # For code: 200-400 (code blocks have natural boundaries)
    chunk_size: int = Field(
        default=500,
        description="Size of each document chunk in characters"
    )

    # Overlap between consecutive chunks.
    # WHY: Without overlap, a sentence split at a chunk boundary loses
    # meaning when the two chunks are retrieved separately.
    # Rule of thumb: overlap = ~10% of chunk_size
    chunk_overlap: int = Field(
        default=50,
        description="Character overlap between consecutive chunks"
    )

    # How many recent messages to include as conversation context.
    # More = better context for multi-turn conversations.
    # Each message costs ~150 tokens, so 10 messages = ~1500 extra tokens/request
    max_history_messages: int = Field(
        default=10,
        description="Max number of recent messages to include in context"
    )

    # ---------------------------------------------------------------
    # Logging Settings
    # ---------------------------------------------------------------

    log_level: str = Field(
        default="INFO",
        description="Logging level: DEBUG | INFO | WARNING | ERROR"
    )

    log_file: str = Field(
        default="./logs/app.log",
        description="Path to log file"
    )

    # ---------------------------------------------------------------
    # Computed Properties
    # Not env vars — derived from other settings.
    # ---------------------------------------------------------------

    @property
    def is_production(self) -> bool:
        """Use this to guard debug-only behavior."""
        return self.app_env == "production"

    @property
    def is_development(self) -> bool:
        return self.app_env == "development"

    @property
    def chroma_persist_path(self) -> Path:
        """Returns the ChromaDB path as a proper Path object."""
        return Path(self.chroma_persist_dir)

    @property
    def log_file_path(self) -> Path:
        return Path(self.log_file)

    # ---------------------------------------------------------------
    # Validators — run at startup to catch bad config early.
    # ---------------------------------------------------------------

    @validator("app_env")
    def validate_app_env(cls, v):
        allowed = {"development", "staging", "production"}
        if v not in allowed:
            raise ValueError(
                f"app_env must be one of {allowed}, got '{v}'"
            )
        return v

    @validator("log_level")
    def validate_log_level(cls, v):
        allowed = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(
                f"log_level must be one of {allowed}, got '{v}'"
            )
        return upper

    @validator("retrieval_top_k")
    def validate_top_k(cls, v):
        if v < 1:
            raise ValueError("retrieval_top_k must be at least 1")
        if v > 20:
            raise ValueError("retrieval_top_k > 20 is rarely useful and wastes tokens")
        return v

    @validator("chunk_overlap")
    def validate_overlap(cls, v, values):
        chunk_size = values.get("chunk_size", 500)
        if v >= chunk_size:
            raise ValueError(
                f"chunk_overlap ({v}) must be less than chunk_size ({chunk_size})"
            )
        return v

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"
        case_sensitive = False


# ---------------------------------------------------------------
# The singleton pattern — IMPORTANT.
#
# @lru_cache means get_settings() returns the SAME Settings object
# every time it is called. Pydantic only reads .env ONCE at startup.
#
# WITHOUT caching: every request re-reads the .env file from disk,
# re-validates all values, creates a new Settings object. Slow.
#
# WITH caching: reads once, returns the same object forever.
#
# HOW TO USE IN OTHER FILES:
#   from config.settings import get_settings
#   settings = get_settings()
#   print(settings.openai_api_key)
#
# IN TESTS — override like this:
#   from unittest.mock import patch
#   with patch("config.settings.get_settings") as mock:
#       mock.return_value = Settings(openai_api_key="test-key", ...)
# ---------------------------------------------------------------

@lru_cache()
def get_settings() -> Settings:
    """
    Returns the application settings singleton.
    lru_cache ensures .env is only read once at startup.
    """
    return Settings()