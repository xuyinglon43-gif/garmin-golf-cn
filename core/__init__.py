"""garmin-golf-cn 核心模块"""

from core.sg import (
    StrokesGainedResult,
    Shot,
    Round,
    calculate_round_sg,
    load_baseline,
)

__version__ = "0.1.0"
__all__ = [
    "StrokesGainedResult",
    "Shot",
    "Round",
    "calculate_round_sg",
    "load_baseline",
]
