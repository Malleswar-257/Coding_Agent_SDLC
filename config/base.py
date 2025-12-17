"""
Base configuration class that aggregates all configuration sections.
"""

import os
from dataclasses import dataclass, field
from typing import Dict, Any

from utils.llm_manager import LLMConfig
from .app_config import BackendConfig, FrontendConfig, ValidationConfig, PathsConfig


@dataclass
class Config:
    """Centralized configuration for the entire application"""
    
    # LLM Configuration
    llm: LLMConfig = field(default_factory=LLMConfig)
    
    # Backend Configuration
    backend: BackendConfig = field(default_factory=BackendConfig)
    
    # Frontend Configuration
    frontend: FrontendConfig = field(default_factory=FrontendConfig)
    
    # Validation Configuration
    validation: ValidationConfig = field(default_factory=ValidationConfig)
    
    # Path Configuration
    paths: PathsConfig = field(default_factory=PathsConfig)
    
    # General Settings
    debug: bool = field(default=False, init=False)
    log_level: str = field(default="INFO", init=False)
    
    def __post_init__(self):
        """Load general settings from environment"""
        self.debug = os.getenv("DEBUG", "false").lower() == "true"
        self.log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert config to dictionary for debugging/logging"""
        return {
            "llm": {
                "primary_model": self.llm.primary_model,
                "fallback_model": self.llm.fallback_model,
                "max_tokens": self.llm.max_tokens,
                "temperature": self.llm.temperature,
                "timeout": self.llm.timeout,
            },
            "backend": {
                "default_stack": self.backend.default_stack,
                "default_port": self.backend.default_port,
                "max_retry_attempts": self.backend.max_retry_attempts,
            },
            "frontend": {
                "default_port": self.frontend.default_port,
                "analyze_api_calls": self.frontend.analyze_api_calls,
            },
            "validation": {
                "strict_mode": self.validation.strict_mode,
                "validate_code": self.validation.validate_code,
            },
            "paths": {
                "project_base_dir": str(self.paths.project_base_dir),
                "temp_dir": str(self.paths.temp_dir),
            },
            "debug": self.debug,
            "log_level": self.log_level,
        }

