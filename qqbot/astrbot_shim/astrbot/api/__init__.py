import logging

logger = logging.getLogger("astrbot")
if not logger.handlers:
    logger.addHandler(logging.NullHandler())
