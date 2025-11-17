"""
Models package for Pixel Prompt Complete.
Provides model registry and provider-specific handlers.
"""

from .registry import ModelRegistry, detect_provider

__all__ = ['ModelRegistry', 'detect_provider']
