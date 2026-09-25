from typing import Any
import logging

logger = logging.getLogger(__name__)

def metadata() -> Any:
    return {
        "font-size": 50,
        "font-color": (200, 150, 70),
    }
