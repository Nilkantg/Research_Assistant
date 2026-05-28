# app/main.py
#
# WHY THIS FILE EXISTS:
# This is the entry point — the first Python file that runs when you start
# the server. Its job is to wire everything together:
#   1. Load configuration
#   2. Set up logging
#   3. Ensure required directories exist
#   4. Create the FastAPI app
#   5. Register routes
#   6. Define startup/shutdown behavior
#
# It intentionally contains NO business logic. It just wires things together.

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from config import get_settings
from utils import setup_logging

# ---------------------------------------------------------------
# Get settings singleton.
# This triggers the .env file read and validation.
# If OPENAI_API_KEY is missing, this raises a clear error RIGHT HERE,
# before any routes are registered or any user traffic is handled.
# ---------------------------------------------------------------
settings = get_settings()

# ---------------------------------------------------------------
# Set up logging BEFORE anything else.
# Every module that imports logging.getLogger(__name__) after this
# point will automatically use this configuration.
# ---------------------------------------------------------------
setup_logging(
    log_level=settings.log_level,
    log_file=settings.log_file
)

logger = logging.getLogger(__name__)


def ensure_directories() -> None:
    """
    Create required directories if they don't exist.

    Why do this explicitly? Because:
    - ChromaDB will crash with a confusing error if its directory is missing
    - Log files can't be written if the logs/ dir doesn't exist
    - Better to fail with a clear message than a cryptic IOError later

    Path.mkdir(parents=True, exist_ok=True) is idempotent —
    safe to call whether the directory exists or not.
    """
    dirs = [
        Path("data/uploads"),
        Path("data/chroma_db"),
        Path("logs"),
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
        logger.debug(f"Directory ready: {d}")


# ---------------------------------------------------------------
# Lifespan context manager — FastAPI's way to handle startup/shutdown.
#
# WHY USE LIFESPAN INSTEAD OF @app.on_event("startup"):
# on_event is deprecated in newer FastAPI versions. Lifespan is the
# modern approach and it's cleaner — startup and shutdown logic live
# together in one function.
#
# Everything before `yield` runs at startup.
# Everything after `yield` runs at shutdown.
# ---------------------------------------------------------------
@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- STARTUP ---
    logger.info("=" * 50)
    logger.info("AI Research Assistant starting up")
    logger.info(f"Environment: {settings.app_env}")
    logger.info(f"Chat model: {settings.openai_chat_model}")
    logger.info(f"Embedding model: {settings.openai_embedding_model}")
    logger.info("=" * 50)

    # Create required directories
    ensure_directories()
    logger.info("Directories verified")

    # Future: initialize DB connection pool here
    # Future: warm up the embedding model here
    # Future: verify ChromaDB connection here

    logger.info("Startup complete — ready to handle requests")

    yield  # App runs here, handling requests

    # --- SHUTDOWN ---
    logger.info("Shutting down AI Research Assistant")
    # Future: close DB connections here
    # Future: flush any pending logs here
    logger.info("Shutdown complete")


# ---------------------------------------------------------------
# Create the FastAPI application.
#
# The lifespan parameter wires our startup/shutdown logic.
# Title and description appear in the auto-generated API docs
# at http://localhost:8000/docs
# ---------------------------------------------------------------
def create_app() -> FastAPI:
    """
    Application factory pattern.

    WHY A FACTORY FUNCTION:
    Returning the app from a function (rather than creating it as a
    module-level variable) makes testing easier. Tests can call
    create_app() to get a fresh app instance without side effects
    from module-level code running.
    """
    app = FastAPI(
        title="AI Research Assistant",
        description="Chat with your documents using RAG + conversation memory",
        version="1.0.0",
        lifespan=lifespan,
        # In production, disable the docs endpoint for security:
        # docs_url=None if settings.is_production else "/docs"
        docs_url="/docs",
        redoc_url="/redoc",
    )

    # ---------------------------------------------------------------
    # CORS middleware.
    # Required when your frontend (Streamlit/React) runs on a different
    # port than your API (e.g., frontend on :8501, API on :8000).
    #
    # In production: replace "*" with your actual frontend domain.
    # Allowing all origins in production is a security risk.
    # ---------------------------------------------------------------
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"] if settings.is_development else ["https://yourdomain.com"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # ---------------------------------------------------------------
    # Register route modules.
    # Each router handles a group of related endpoints.
    # We'll build these in later steps.
    # ---------------------------------------------------------------
    # from api.routes.chat import router as chat_router
    # from api.routes.documents import router as documents_router
    # app.include_router(chat_router, prefix="/api/v1", tags=["chat"])
    # app.include_router(documents_router, prefix="/api/v1", tags=["documents"])

    # ---------------------------------------------------------------
    # Health check endpoint.
    # Every production service needs this. Load balancers and
    # Kubernetes use it to know if the service is alive and ready.
    # ---------------------------------------------------------------
    @app.get("/health", tags=["system"])
    async def health_check():
        return {
            "status": "healthy",
            "environment": settings.app_env,
            "version": "1.0.0"
        }

    @app.get("/", tags=["system"])
    async def root():
        return {
            "message": "AI Research Assistant API",
            "docs": "/docs"
        }

    return app


# Create the app instance
app = create_app()


# ---------------------------------------------------------------
# Entry point for running directly with `python app/main.py`
# In production you'd use: uvicorn app.main:app --host 0.0.0.0 --port 8000
# ---------------------------------------------------------------
if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "app.main:app",
        host=settings.app_host,
        port=settings.app_port,
        reload=settings.is_development,  # Auto-reload on code changes in dev
        log_level=settings.log_level.lower()
    )