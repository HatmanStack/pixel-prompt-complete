"""
Jobs package for Pixel Prompt Complete.
Provides job lifecycle management and parallel execution.
"""

from .manager import JobManager
from .executor import JobExecutor

__all__ = ['JobManager', 'JobExecutor']
