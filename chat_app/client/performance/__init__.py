"""
Client Performance Optimization Module

Performance optimizations for the chat client including UI rendering,
input handling, and network communication efficiency.
"""

from .ui_optimizer import UIOptimizer, UIConfig, RenderStats
from .update_scheduler import UpdateScheduler, UpdateConfig, UpdatePriority

__all__ = [
    'UIOptimizer',
    'UIConfig', 
    'RenderStats',
    'UpdateScheduler',
    'UpdateConfig',
    'UpdatePriority'
]