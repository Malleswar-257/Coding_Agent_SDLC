"""
Centralized configuration for CODE AGENT.

All configuration values can be overridden via environment variables.
Default values are provided for all settings.
"""

from .base import Config

# Create singleton config instance
config = Config()

__all__ = ['config', 'Config']

