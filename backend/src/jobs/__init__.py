"""
Jobs package for Pixel Prompt Complete.
Provides job lifecycle management and parallel execution.
"""

from .executor import JobExecutor
from .manager import JobManager

__all__ = ['JobManager', 'JobExecutor']
