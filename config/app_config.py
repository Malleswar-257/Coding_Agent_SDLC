"""
Application Configuration - Unified configuration module
Consolidates BackendConfig, FrontendConfig, ValidationConfig, and PathsConfig into a single efficient module.
"""

import os
import tempfile
from pathlib import Path
from dataclasses import dataclass, field
from typing import Dict, List


@dataclass
class BackendConfig:
    """Backend generation configuration"""
    
    # Supported stacks
    supported_stacks: List[str] = field(default_factory=lambda: [
        "FastAPI + SQLAlchemy",
        "Django"
    ])
    
    # Default stack
    default_stack: str = "FastAPI + SQLAlchemy"
    
    # Port configuration
    default_port: int = field(default=8000, init=False)
    
    # Code generation settings
    max_retry_attempts: int = field(default=3, init=False)
    code_indent_size: int = 4
    
    # Package requirements
    required_packages: Dict[str, str] = field(default_factory=lambda: {
        "pydantic": ">=2.7.4",  # Required for langchain compatibility
        "python-dotenv": ">=1.0.0",
    })
    
    # FastAPI specific
    fastapi_version: str = ">=0.104.0"
    uvicorn_version: str = ">=0.24.0"
    sqlalchemy_version: str = ">=2.0.0"
    
    # Django specific
    django_version: str = ">=5.0.0"
    djangorestframework_version: str = ">=3.15.0"
    
    # File validation
    validate_syntax: bool = True
    fix_code_automatically: bool = True
    max_file_size_mb: int = 10
    
    def __post_init__(self):
        """Load settings from environment"""
        self.default_port = int(os.getenv("BACKEND_PORT", "8000"))
        self.max_retry_attempts = int(os.getenv("BACKEND_MAX_RETRIES", "3"))
        
        # Allow environment to override default stack
        if os.getenv("BACKEND_STACK"):
            self.default_stack = os.getenv("BACKEND_STACK")


@dataclass
class FrontendConfig:
    """Frontend analysis configuration"""
    
    # Supported frameworks
    supported_frameworks: List[str] = field(default_factory=lambda: [
        "react",
        "vue",
        "nextjs",
        "svelte"
    ])
    
    # Port configuration
    default_port: int = field(default=3000, init=False)
    
    # Analysis settings
    analyze_api_calls: bool = True
    analyze_form_fields: bool = True
    analyze_components: bool = True
    analyze_routes: bool = True
    use_llm_enhancement: bool = False  # Use LLM for complex analysis
    
    # API detection patterns
    api_call_patterns: Dict[str, List[str]] = field(default_factory=lambda: {
        "react": ["fetch(", "axios.", "useEffect"],
        "vue": ["this.$http", "axios.", "$fetch"],
        "nextjs": ["fetch(", "axios.", "useSWR"],
        "svelte": ["fetch(", "axios."]
    })
    
    # File patterns to analyze
    code_file_extensions: List[str] = field(default_factory=lambda: [
        ".js", ".jsx", ".ts", ".tsx", ".vue", ".svelte"
    ])
    
    # Ignore patterns
    ignore_patterns: List[str] = field(default_factory=lambda: [
        "node_modules",
        ".next",
        ".nuxt",
        "dist",
        "build"
    ])
    
    def __post_init__(self):
        """Load settings from environment"""
        self.default_port = int(os.getenv("FRONTEND_PORT", "3000"))
        self.use_llm_enhancement = os.getenv("USE_LLM_FRONTEND_ANALYSIS", "false").lower() == "true"


@dataclass
class ValidationConfig:
    """Validation settings"""
    
    # Strict mode (errors block workflow)
    strict_mode: bool = field(default=False, init=False)
    
    # Validation levels
    validate_spec: bool = True
    validate_code: bool = True
    validate_integration: bool = True
    
    # Code validation settings
    check_syntax: bool = True
    check_imports: bool = True
    check_endpoints: bool = True
    check_required_files: bool = True
    
    # Integration validation settings
    check_connectivity: bool = True
    check_environment: bool = True
    check_cors: bool = True
    check_endpoints_accessible: bool = False  # Requires running server
    
    def __post_init__(self):
        """Load settings from environment"""
        self.strict_mode = os.getenv("VALIDATION_STRICT_MODE", "false").lower() == "true"
        self.check_endpoints_accessible = os.getenv("VALIDATION_CHECK_ENDPOINTS", "false").lower() == "true"


@dataclass
class PathsConfig:
    """Path and directory configuration"""
    
    # Base directories
    project_base_dir: Path = field(default=None, init=False)
    temp_dir: Path = field(default=None, init=False)
    
    # Project structure
    frontend_dir_name: str = "frontend"
    backend_dir_name: str = "backend"
    
    # File names
    requirements_file: str = "requirements.txt"
    env_example_file: str = ".env.example"
    readme_file: str = "README.md"
    gitignore_file: str = ".gitignore"
    docker_compose_file: str = "docker-compose.yml"
    
    def __post_init__(self):
        """Load paths from environment"""
        # Get project base directory from environment or use default
        project_base = os.getenv("PROJECT_BASE_DIR", "./projects")
        self.project_base_dir = Path(project_base)
        
        # Get temp directory from environment or use system default
        temp_base = os.getenv("TEMP_DIR", tempfile.gettempdir())
        self.temp_dir = Path(temp_base)
    
    def get_project_path(self, project_name: str) -> Path:
        """Get full path for a project"""
        return self.project_base_dir / project_name
    
    def get_temp_project_path(self, project_name: str) -> Path:
        """Get temporary path for a project"""
        return self.temp_dir / f"{project_name}_temp"



