# app/main.py
#
# WHY THIS FILE EXISTS:
# This is the entry point — the first Python file that runs when you start
# the server. Its only job is to wire everything together:
#   1. Load configuration
#   2. Set up logging
#   3. Ensure required directories exist
#   4. Initialize the database
#   5. Create the FastAPI app
#   6. Register routes
#   7. Define startup / shutdown behavior
#
# This file contains NO business logic. It only wires things together.
# Business logic lives in chains/, retrievers/, memory/, etc.

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from database import init_database
from utils import setup_logging

# ---------------------------------------------------------------
# Load settings FIRST — before anything else runs.
#
# If OPENAI_API_KEY is missing from the environment, Pydantic
# raises a ValidationError RIGHT HERE, before routes are registered
# or any traffic is served. This is "fail fast" — you want to know
# about misconfiguration at startup, not at 2am when a user hits
# a broken endpoint.
# ---------------------------------------------------------------
settings = get_settings()

# ---------------------------------------------------------------
# Set up logging SECOND — before any other imports log anything.
#
# After this call, every module that does:
#   logger = logging.getLogger(__name__)
# will automatically use this configuration (correct format,
# correct level, writing to both console and file).
# ---------------------------------------------------------------
setup_logging(
    log_level=settings.log_level,
    log_file=settings.log_file,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------
# Directory setup
# ---------------------------------------------------------------

def ensure_directories() -> None:
    """
    Create required directories if they don't exist yet.

    Called at startup before anything tries to write to these paths.
    Path.mkdir(parents=True, exist_ok=True) is fully idempotent —
    safe to call on directories that already exist.

    Why bother? ChromaDB gives a cryptic IOError if its persist
    directory is missing. The logs handler silently fails. Explicit
    directory creation with a clear log message is much easier to debug.
    """
    required_dirs = [
        Path("data/uploads"),    # Uploaded PDF/document files
        Path("data/chroma_db"),  # ChromaDB vector store files
        Path("logs"),            # Application log files
    ]

    for directory in required_dirs:
        directory.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Directory ready: {directory}")


# ---------------------------------------------------------------
# Lifespan — FastAPI's modern startup/shutdown pattern.
#
# Everything BEFORE yield runs at startup.
# Everything AFTER yield runs at shutdown.
#
# Why lifespan instead of @app.on_event("startup"):
# on_event is deprecated in FastAPI 0.93+. Lifespan is cleaner —
# startup and shutdown code are co-located in one function,
# and it supports async context managers properly.
# ---------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    # ==================== STARTUP ====================
    logger.info("=" * 50)
    logger.info("AI Research Assistant — starting up")
    logger.info(f"  Environment : {settings.app_env}")
    logger.info(f"  Chat model  : {settings.openai_chat_model}")
    logger.info(f"  Embed model : {settings.openai_embedding_model}")
    logger.info(f"  Top-K       : {settings.retrieval_top_k}")
    logger.info("=" * 50)

    # Step 1 — directories
    ensure_directories()
    logger.info("Directories verified")

    # Step 2 — database
    # Creates tables if they don't exist. Safe to call every startup.
    init_database()
    logger.info("Database ready")

    # Step 3 (future) — warm up embedding model
    # Calling the embedding model once at startup loads it into memory
    # so the first real user request isn't slow.
    # from vectorstore import get_chroma_store
    # get_chroma_store()  # initializes ChromaDB client

    logger.info("Startup complete — ready to handle requests")

    yield  # ← Application runs here, handling all requests

    # ==================== SHUTDOWN ====================
    logger.info("Shutting down AI Research Assistant")
    # Future: gracefully close async DB engine
    # await async_engine.dispose()
    logger.info("Shutdown complete")


# ---------------------------------------------------------------
# Application factory
#
# WHY A FACTORY FUNCTION instead of a module-level `app = FastAPI(...)`:
# Tests call create_app() to get a fresh application instance each time.
# Module-level instantiation causes side effects (middleware, routes)
# to run once when the module is first imported, which makes isolated
# testing harder.
# ---------------------------------------------------------------

def create_app() -> FastAPI:
    """
    Build and return the configured FastAPI application.

    This is the only place where middleware and routes are registered.
    """

    app = FastAPI(
        title="AI Research Assistant",
        description=(
            "Upload documents, chat with them using RAG, "
            "with full conversation memory and source citations."
        ),
        version="1.0.0",
        lifespan=lifespan,
        # Tip: in production, disable Swagger UI to reduce attack surface:
        # docs_url=None if settings.is_production else "/docs",
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ---------------------------------------------------------------
    # CORS middleware
    #
    # Required when the frontend runs on a different origin than
    # the API. Example: Streamlit on :8501, FastAPI on :8000.
    #
    # In production: replace "*" with your actual frontend domain.
    # Allowing all origins in production is a real security risk.
    # ---------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=(
            ["*"]
            if settings.is_development
            else ["https://yourdomain.com"]
        ),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------------------------------------------------------------
    # Route registration
    #
    # We'll uncomment these as we build each router in later steps.
    # Using prefix="/api/v1" means all endpoints are versioned —
    # you can add /api/v2 later without breaking existing clients.
    # ---------------------------------------------------------------
    # from api.routes.chat import router as chat_router
    # from api.routes.documents import router as documents_router
    # app.include_router(chat_router, prefix="/api/v1", tags=["chat"])
    # app.include_router(documents_router, prefix="/api/v1", tags=["documents"])

    # ---------------------------------------------------------------
    # System endpoints
    # ---------------------------------------------------------------

    @app.get("/health", tags=["system"])
    async def health_check():
        """
        Liveness probe for load balancers and Kubernetes.
        Returns 200 if the service is running and configured correctly.
        """
        return {
            "status": "healthy",
            "environment": settings.app_env,
            "version": "1.0.0",
        }

    @app.get("/", tags=["system"])
    async def root():
        return {
            "message": "AI Research Assistant API",
            "docs": "/docs",
        }

    return app


# ---------------------------------------------------------------
# Module-level app instance
# Uvicorn and other ASGI servers look for this by convention:
#   uvicorn app.main:app
# ---------------------------------------------------------------
app = create_app()


# ---------------------------------------------------------------
# Direct execution entry point
# For development: python app/main.py
# For production:  uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
# ---------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.is_development,   # Hot-reload on code changes in dev only
        log_level=settings.log_level.lower(),
    )