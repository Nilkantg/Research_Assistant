# utils/logging.py
#
# WHY STRUCTURED LOGGING MATTERS IN PRODUCTION:
#
# print() is fine for scripts. For a production server handling many users,
# you need to know:
#   - WHEN something happened (timestamp)
#   - WHAT happened (message)
#   - WHERE it happened (which module/function)
#   - HOW SEVERE it is (DEBUG / INFO / WARNING / ERROR)
#   - WHICH REQUEST caused it (request_id, session_id)
#
# Python's logging module gives you all of this for free — you just need
# to configure it once, correctly.
#
# The pattern here: one setup function called at app startup.
# Every other module does:
#   import logging
#   logger = logging.getLogger(__name__)
# and gets a properly configured logger automatically.

import logging
import logging.handlers
import sys
from pathlib import Path


def setup_logging(log_level: str = "INFO", log_file: str = "./logs/app.log") -> None:
    """
    Configure application-wide logging.

    Call this ONCE at application startup (in app/main.py).
    After this, every module can just do:
        logger = logging.getLogger(__name__)

    Args:
        log_level: Minimum log level to capture (DEBUG/INFO/WARNING/ERROR)
        log_file: Path to write log file
    """

    # Convert string log level to logging constant
    # e.g. "INFO" -> logging.INFO (which is the integer 20)
    numeric_level = getattr(logging, log_level.upper(), logging.INFO)

    # ---------------------------------------------------------------
    # Formatter — controls what each log line looks like.
    #
    # %(asctime)s    - timestamp: "2024-01-15 14:32:01,123"
    # %(name)s       - logger name (usually the module: "chains.rag_chain")
    # %(levelname)s  - log level: "INFO", "ERROR", etc.
    # %(message)s    - the actual log message
    # %(filename)s   - source file name
    # %(lineno)d     - line number
    # ---------------------------------------------------------------
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s:%(lineno)d | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # ---------------------------------------------------------------
    # Console handler — writes to stdout.
    # In production containers, stdout is captured by the orchestrator
    # (Docker, Kubernetes) and routed to your log aggregation system.
    # ---------------------------------------------------------------
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    console_handler.setLevel(numeric_level)

    # ---------------------------------------------------------------
    # File handler — writes to a rotating log file.
    # RotatingFileHandler automatically creates a new file when the
    # current one gets too large (maxBytes), keeping the last N files
    # (backupCount). This prevents filling up disk in production.
    #
    # 10MB * 5 files = max 50MB of logs on disk. Reasonable.
    # ---------------------------------------------------------------
    log_path = Path(log_file)
    log_path.parent.mkdir(parents=True, exist_ok=True)

    file_handler = logging.handlers.RotatingFileHandler(
        filename=log_path,
        maxBytes=10 * 1024 * 1024,  # 10 MB
        backupCount=5,
        encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(numeric_level)

    # ---------------------------------------------------------------
    # Root logger configuration.
    # Setting the root logger affects ALL loggers in the app,
    # including third-party libraries (LangChain, FastAPI, etc.).
    # ---------------------------------------------------------------
    root_logger = logging.getLogger()
    root_logger.setLevel(numeric_level)
    root_logger.addHandler(console_handler)
    root_logger.addHandler(file_handler)

    # ---------------------------------------------------------------
    # Silence noisy third-party loggers.
    # Libraries like httpx and chromadb log at DEBUG level by default.
    # In development this is useful; in production it's noise.
    # ---------------------------------------------------------------
    logging.getLogger("httpx").setLevel(logging.WARNING)
    logging.getLogger("chromadb").setLevel(logging.WARNING)
    logging.getLogger("langchain").setLevel(logging.WARNING)
    logging.getLogger("openai").setLevel(logging.WARNING)
    logging.getLogger("uvicorn.access").setLevel(logging.WARNING)

    # Log that logging is configured (meta, but useful for debugging)
    logger = logging.getLogger(__name__)
    logger.info(f"Logging configured — level={log_level}, file={log_file}")


def get_logger(name: str) -> logging.Logger:
    """
    Convenience function to get a logger.

    Usage in any module:
        from utils.logging import get_logger
        logger = get_logger(__name__)
        logger.info("Something happened")

    Using __name__ as the logger name means log lines show you
    exactly which module produced them. e.g.:
        2024-01-15 14:32:01 | INFO | chains.rag_chain:45 | Starting retrieval
    """
    return logging.getLogger(name)