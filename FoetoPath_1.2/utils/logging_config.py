"""
FoetoPath structured logging configuration.
"""

import logging
import sys


def setup_logging(level=logging.INFO):
    """Configure structured logging for FoetoPath."""
    fmt = '%(asctime)s [%(name)s] %(levelname)s: %(message)s'
    logging.basicConfig(
        level=level,
        format=fmt,
        datefmt='%Y-%m-%d %H:%M:%S',
        stream=sys.stderr,
    )
    # Reduce noise from third-party libs
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('openslide').setLevel(logging.WARNING)
