import logging
import os
import sys
import traceback

LOG_FILE = os.path.join(os.path.dirname(__file__), "..", "studio.log")

def setup_logger():
    """
    Initializes comprehensive logging for Switch Mod Studio.
    Writes to both studio.log and stdout.
    Installs global crash hooks for sys.excepthook.
    """
    logger = logging.getLogger("SwitchModStudio")
    logger.setLevel(logging.DEBUG)

    # Remove any existing handlers
    logger.handlers.clear()

    # Formatter
    formatter = logging.Formatter(
        "[%(asctime)s] [%(levelname)-7s] [%(filename)s:%(lineno)d] %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )

    # 1. File Handler (with UTF-8 encoding)
    try:
        fh = logging.FileHandler(LOG_FILE, mode="a", encoding="utf-8")
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(formatter)
        logger.addHandler(fh)
    except Exception as e:
        print(f"Warning: Could not create log file: {e}")

    # 2. Console Handler (safe UTF-8)
    if hasattr(sys.stdout, "reconfigure"):
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass
    ch = logging.StreamHandler(sys.stdout)
    ch.setLevel(logging.INFO)
    ch.setFormatter(formatter)
    logger.addHandler(ch)

    # Global Exception Hook
    def handle_uncaught_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        logger.critical("UNCAUGHT EXCEPTION:\n" + "".join(traceback.format_exception(exc_type, exc_value, exc_traceback)))

    sys.excepthook = handle_uncaught_exception

    logger.info("=" * 60)
    logger.info("Polyglot Studio Logger Initialized")
    logger.info(f"Python: {sys.version.split()[0]} | Platform: {sys.platform}")
    logger.info(f"Log File: {os.path.abspath(LOG_FILE)}")
    logger.info("=" * 60)

    return logger

# Singleton logger
log = setup_logger()
