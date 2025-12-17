"""
IntegratorAgent - Combines everything, adds routing, env files, configs, tests, fixes errors
"""

from typing import Dict, Any
from pathlib import Path
import tempfile
import os
import json
import shutil
import subprocess
from utils.logger import StreamlitLogger
from utils.code_fixer import CodeFixer
from utils.connection_manager import ConnectionManager
from utils.package_validator import PackageValidator
from utils.code_fixer import unescape_content

class IntegratorAgent:
    """Agent that integrates frontend and backend into a complete project"""
    
    def __init__(self, llm, logger: StreamlitLogger):
        self.llm = llm
        self.logger = logger
        self.code_fixer = CodeFixer(logger=logger)
        self.connection_manager = ConnectionManager(logger=logger)
        self.package_validator = PackageValidator(logger=logger)
    
    def integrate(
        self,
        project_config: Dict[str, Any],
        backend_code: Dict[str, str],
        project_spec: Dict[str, Any]
    ) -> str:
        """Integrate frontend and backend into a complete project"""
        self.logger.log("🔗 Integrating generated code and scaffolding project...")
        
        # Handle None values and ensure correct types
        if backend_code is None:
            backend_code = {}
        if not isinstance(backend_code, dict):
            self.logger.log(f"⚠️ backend_code is not a dict (type: {type(backend_code)}), converting to dict", level="warning")
            backend_code = {}
        
        if project_spec is None:
            project_spec = {}
        if not isinstance(project_spec, dict):
            self.logger.log(f"⚠️ project_spec is not a dict (type: {type(project_spec)}), converting to dict", level="warning")
            project_spec = {}
        
        # Create temporary project directory
        project_name = project_config["project_name"]
        temp_dir = tempfile.mkdtemp(prefix=f"{project_name}_")
        project_path = Path(temp_dir) / project_name
        project_path.mkdir(parents=True, exist_ok=True)
        
        try:
            # Create project structure
            self.logger.log("📁 Creating project structure...")
            
            # Fetch frontend repo if provided
            self._fetch_frontend_repo(project_config, project_path)
            
            # Write backend files
            if backend_code:
                # Ensure backend_code is a dict
                if not isinstance(backend_code, dict):
                    self.logger.log(f"⚠️ backend_code is not a dict (type: {type(backend_code)}), converting...", level="warning")
                    if isinstance(backend_code, str):
                        # Try to parse as JSON
                        try:
                            import json
                            backend_code = json.loads(backend_code)
                        except:
                            # If parsing fails, create a minimal dict
                            backend_code = {"app/main.py": "# Generated backend code\n"}
                    else:
                        # Convert to dict or use empty dict
                        backend_code = {}
                
                backend_dir = project_path / "backend"
                backend_dir.mkdir(exist_ok=True)
                # Fix common package name mistakes before writing
                backend_code = self.package_validator.fix_python_packages(backend_code)
                self._write_files(backend_dir, backend_code)
                # Add backend integration helpers (CORS/env)
                # CORS will be handled by connection_manager.setup_connections() later
                self._write_backend_env_example(backend_dir)
                # Ensure mandatory .bat files exist
                self._ensure_backend_bat_files(backend_dir, project_config.get("backend_stack", ""))
                self.logger.log(f"✅ Wrote {len(backend_code)} backend files")
            
            # Create root-level files
            self._create_root_files(project_path, project_config, project_spec)
            # Add frontend env for API base URL
            self._write_frontend_env(project_path)
            
            # Setup frontend-backend connections (API services, endpoints, etc.)
            if backend_code and project_path.exists():
                frontend_stack = project_config.get("frontend_stack", "react")
                try:
                    connection_result = self.connection_manager.setup_connections(
                        project_path=project_path,
                        backend_code=backend_code,
                        project_spec=project_spec,
                        frontend_stack=frontend_stack
                    )
                    if connection_result.get("success"):
                        self.logger.log(f"✅ Connected {connection_result.get('endpoints', 0)} endpoints with frontend")
                except Exception as e:
                    self.logger.log(f"⚠️ Error setting up connections: {str(e)}", level="warning")
            
            # Create docker-compose if needed
            if self._needs_docker(project_config["backend_stack"]):
                self._create_docker_compose(project_path, project_config)
            
            # Initialize git
            self._init_git(project_path)
            
            self.logger.log("✅ Project integration completed")
            
            return str(project_path)
            
        except Exception as e:
            self.logger.log(f"⚠️ Error during integration: {str(e)}", level="error")
            raise

    def _fetch_frontend_repo(self, project_config: Dict[str, Any], project_path: Path):
        """Clone frontend repo into project if URL provided"""
        repo_url = project_config.get("frontend_repo_url")
        if not repo_url:
            self.logger.log("ℹ️ No frontend repo URL provided; skipping frontend fetch")
            return
        
        frontend_dir = project_path / "frontend"
        if frontend_dir.exists():
            shutil.rmtree(frontend_dir, ignore_errors=True)
        try:
            self.logger.log(f"📥 Cloning frontend repo: {repo_url}")
            subprocess.run(
                ["git", "clone", "--depth", "1", repo_url, str(frontend_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
            # Remove git metadata to keep package clean
            git_dir = frontend_dir / ".git"
            if git_dir.exists():
                shutil.rmtree(git_dir, ignore_errors=True)
            self.logger.log("✅ Frontend repo cloned into project/frontend")
        except subprocess.CalledProcessError as e:
            self.logger.log(
                f"⚠️ Failed to clone frontend repo ({repo_url}): {e.stderr or e.stdout}",
                level="error",
            )
        except Exception as e:
            self.logger.log(f"⚠️ Unexpected error cloning frontend repo: {str(e)}", level="error")
    
    def _unescape_content(self, content: str) -> str:
        """Unescape escape sequences in file content - uses shared utility with additional fixes"""
        # Use shared utility for basic unescaping
        content = unescape_content(content)
        
        # Additional fix: handle double-escaped sequences (\\\\n -> \n -> newline)
        # This can happen when content is serialized multiple times
        if '\\\\n' in content or '\\\\t' in content:
            content = content.replace('\\\\n', '\n').replace('\\\\t', '\t')
        
        return content
    
    def _validate_html_files(self, files: Dict[str, str]) -> Dict[str, str]:
        """Validate and fix incomplete HTML files"""
        fixed_files = files.copy()
        
        for file_path, content in fixed_files.items():
            if file_path.endswith('.html') or file_path.endswith('.htm'):
                fixed_content = self._unescape_content(content)
                
                # Check if HTML is complete
                has_doctype = '<!DOCTYPE' in fixed_content or '<!doctype' in fixed_content
                has_html_open = '<html' in fixed_content
                has_html_close = '</html>' in fixed_content
                has_head_close = '</head>' in fixed_content
                has_body_open = '<body' in fixed_content
                has_body_close = '</body>' in fixed_content
                
                # If HTML appears incomplete, try to fix it
                if has_html_open and (not has_html_close or not has_body_close):
                    self.logger.log(f"⚠️ HTML file {file_path} appears incomplete, attempting to fix...")
                    
                    # Try to complete the HTML
                    if not has_doctype:
                        fixed_content = '<!DOCTYPE html>\n' + fixed_content
                    
                    if '<html' in fixed_content and '</html>' not in fixed_content:
                        # Add missing closing tags
                        if '<body' in fixed_content and '</body>' not in fixed_content:
                            # Add closing body tag
                            if '<div id="root">' in fixed_content or '<div id="app">' in fixed_content:
                                # React/Vue app - add script tag if missing
                                if '<script' not in fixed_content or 'src=' not in fixed_content:
                                    # Try to find the main entry point
                                    main_js = '/src/main.jsx' if 'main.jsx' in str(files.keys()) else '/src/main.js'
                                    fixed_content += f'\n    <script type="module" src="{main_js}"></script>'
                            fixed_content += '\n</body>'
                        
                        if '</head>' not in fixed_content and '<head' in fixed_content:
                            # Head tag not closed, try to close it
                            if '</head>' not in fixed_content:
                                # Find where head should close (before body)
                                if '<body' in fixed_content:
                                    fixed_content = fixed_content.replace('<body', '</head>\n<body', 1)
                                else:
                                    fixed_content += '\n</head>'
                        
                        fixed_content += '\n</html>'
                    
                    fixed_files[file_path] = fixed_content
                    self.logger.log(f"🔧 Fixed incomplete HTML file: {file_path}")
        
        return fixed_files
    
    def _write_files(self, base_dir: Path, files: Dict[str, str]):
        """Write files to directory structure"""
        for file_path, content in files.items():
            # Normalize path
            if file_path.startswith("/"):
                file_path = file_path[1:]
            
            full_path = base_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            
            # Unescape content (handle \n -> newline, etc.)
            unescaped_content = self._unescape_content(content)
            
            # Fix Python code formatting if it's a Python file
            if file_path.endswith('.py'):
                unescaped_content = self._fix_python_code(unescaped_content, file_path)
            
            # Write file
            with open(full_path, "w", encoding="utf-8") as f:
                f.write(unescaped_content)
    
    def _fix_python_code(self, code: str, file_path: str) -> str:
        """Fix Python code formatting and indentation"""
        # Use CodeFixer for comprehensive fixing (includes indentation)
        return self.code_fixer.validate_and_fix(code, file_path, max_attempts=5)
    
    def _fix_syntax_errors(self, code: str, syntax_error: SyntaxError, file_path: str = "") -> str:
        """Attempt to fix common syntax errors - delegates to CodeFixer"""
        # All syntax fixing logic is now in CodeFixer
        return self.code_fixer.fix_syntax_error(code, syntax_error, file_path)
    
    
    def _create_root_files(self, project_path: Path, project_config: Dict[str, Any], project_spec: Dict[str, Any]):
        """Create root-level project files"""
        # Ensure project_spec is a dict
        if not isinstance(project_spec, dict):
            project_spec = {}
        
        # Ensure project_config is a dict
        if not isinstance(project_config, dict):
            project_config = {}
        
        # README.md
        features_list = project_spec.get('features', []) if isinstance(project_spec, dict) else []
        api_endpoints_list = project_spec.get('api_endpoints', []) if isinstance(project_spec, dict) else []
        
        features_text = chr(10).join(f"- {feature}" for feature in features_list) if features_list else "- No features specified"
        endpoints_text = chr(10).join(f"- `{ep.get('method', 'GET') if isinstance(ep, dict) else 'GET'} {ep.get('path', '/') if isinstance(ep, dict) else '/'}` - {ep.get('description', '') if isinstance(ep, dict) else ''}" for ep in api_endpoints_list[:10]) if api_endpoints_list else "- No API endpoints specified"
        
        readme_content = f"""# {project_config.get('project_name', 'Project')}

{project_config.get('description', 'Generated project')}

## Tech Stack

- **Backend**: {project_config.get('backend_stack', 'Not specified')}
- **Frontend**: Provided via GitHub repo ({project_config.get('frontend_repo_url', 'not provided')})

## Project Structure

```
{project_config.get('project_name', 'project')}/
├── frontend/           # Frontend (cloned from provided repo)
├── backend/            # Backend API
├── README.md           # This file
└── docker-compose.yml  # Docker configuration (if applicable)
```

## Getting Started

### Prerequisites

- Python 3.11+ (for Python backends)
- Docker (optional, for containerized setup)
- Node.js 18+ (for frontend from repo)

### Backend Setup

```bash
cd backend
# Follow backend-specific setup instructions in backend/README.md
python -m venv .venv
source .venv/bin/activate  # or .venv\\Scripts\\activate on Windows
pip install -r requirements.txt
uvicorn app.main:app --reload
```

### Frontend Setup (from provided repo)

```bash
cd frontend
npm install
npm run dev
```

## Features

{features_text}

## API Endpoints

{endpoints_text}

## License

MIT
"""
        
        with open(project_path / "README.md", "w", encoding="utf-8") as f:
            f.write(readme_content)
        
        # .gitignore
        gitignore_content = """# Dependencies
node_modules/
__pycache__/
*.pyc
*.pyo
*.pyd
.Python
env/
venv/
ENV/

# Build outputs
dist/
build/
*.egg-info/

# Environment variables
.env
.env.local

# IDE
.vscode/
.idea/
*.swp
*.swo

# OS
.DS_Store
Thumbs.db

# Logs
*.log
"""
        
        with open(project_path / ".gitignore", "w", encoding="utf-8") as f:
            f.write(gitignore_content)
    
    def _needs_docker(self, backend_stack: str) -> bool:
        """Check if backend stack needs Docker"""
        return "FastAPI" in backend_stack or "Django" in backend_stack or "Node.js" in backend_stack
    
    def _create_docker_compose(self, project_path: Path, project_config: Dict[str, Any]):
        """Create docker-compose.yml file"""
        frontend_port = project_config.get("frontend_port", "3000")
        backend_port = project_config.get("backend_port", "8000")
        docker_content = f"""version: '3.8'

services:
  backend:
    build: ./backend
    ports:
      - "{backend_port}:8000"
    environment:
      - DATABASE_URL=postgresql://user:password@db:5432/dbname
      - FRONTEND_ORIGIN=http://localhost:{frontend_port}
      - BACKEND_PORT=8000
    depends_on:
      - db
  
  frontend:
    build: ./frontend
    ports:
      - "{frontend_port}:3000"
    environment:
      - API_BASE_URL=http://localhost:{backend_port}
      - VITE_API_BASE_URL=http://localhost:{backend_port}
      - NEXT_PUBLIC_API_BASE_URL=http://localhost:{backend_port}
      - REACT_APP_API_BASE_URL=http://localhost:{backend_port}
      - NUXT_PUBLIC_API_BASE_URL=http://localhost:{backend_port}
    depends_on:
      - backend
  
  db:
    image: postgres:15
    environment:
      - POSTGRES_USER=user
      - POSTGRES_PASSWORD=password
      - POSTGRES_DB=dbname
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
"""
        
        with open(project_path / "docker-compose.yml", "w", encoding="utf-8") as f:
            f.write(docker_content)

    def _write_frontend_env(self, project_path: Path):
        """Write frontend env file with API base URLs for common frameworks"""
        frontend_dir = project_path / "frontend"
        if not frontend_dir.exists():
            return
        env_content = "\n".join([
            "API_BASE_URL=http://localhost:8000",
            "VITE_API_BASE_URL=http://localhost:8000",
            "NEXT_PUBLIC_API_BASE_URL=http://localhost:8000",
            "REACT_APP_API_BASE_URL=http://localhost:8000",
            "NUXT_PUBLIC_API_BASE_URL=http://localhost:8000",
            ""
        ])
        try:
            with open(frontend_dir / ".env", "w", encoding="utf-8") as f:
                f.write(env_content)
            self.logger.log("✅ Added frontend .env with API base URLs")
        except Exception as e:
            self.logger.log(f"⚠️ Could not write frontend .env: {str(e)}", level="error")

    def _write_backend_env_example(self, backend_dir: Path):
        """Ensure backend has env example with frontend origin"""
        env_example = backend_dir / ".env.example"
        # Preserve existing content if present
        existing = ""
        if env_example.exists():
            try:
                existing = env_example.read_text(encoding="utf-8")
            except Exception:
                existing = ""
        if "FRONTEND_ORIGIN" not in existing:
            content = existing.strip() + ("\n" if existing else "")
            content += "FRONTEND_ORIGIN=http://localhost:3000\nBACKEND_PORT=8000\n"
            try:
                env_example.write_text(content, encoding="utf-8")
                self.logger.log("✅ Added FRONTEND_ORIGIN to backend .env.example")
            except Exception as e:
                self.logger.log(f"⚠️ Could not update backend .env.example: {str(e)}", level="error")

    def _ensure_backend_bat_files(self, backend_dir: Path, backend_stack: str):
        """Ensure mandatory .bat files exist for Windows users"""
        self.logger.log("📝 Ensuring mandatory .bat files exist...")
        
        # Check if any .bat files already exist
        existing_bat_files = list(backend_dir.glob("*.bat"))
        
        # Create setup.bat if missing
        setup_bat = backend_dir / "setup.bat"
        if not setup_bat.exists():
            setup_bat_content = """@echo off
echo Installing backend dependencies...
cd /d "%~dp0"
python -m venv .venv
call .venv\\Scripts\\activate.bat
pip install --upgrade pip
pip install -r requirements.txt
echo.
echo Setup complete! Activate virtual environment with: .venv\\Scripts\\activate.bat
pause
"""
            setup_bat.write_text(setup_bat_content, encoding='utf-8')
            self.logger.log("✅ Created setup.bat")
        
        # Create run.bat based on backend stack
        run_bat = backend_dir / "run.bat"
        if not run_bat.exists():
            if "fastapi" in backend_stack.lower() or "fastapi" in str(backend_dir):
                # Try to detect main file location
                main_paths = [
                    backend_dir / "app" / "main.py",
                    backend_dir / "main.py",
                    backend_dir / "src" / "main.py"
                ]
                main_file = None
                for path in main_paths:
                    if path.exists():
                        # Calculate relative path from backend_dir
                        rel_path = path.relative_to(backend_dir)
                        main_file = str(rel_path).replace("\\", ".").replace(".py", "")
                        break
                
                if not main_file:
                    main_file = "app.main"  # Default
                
                run_bat_content = f"""@echo off
echo Starting FastAPI server...
cd /d "%~dp0"
if not exist .venv\\Scripts\\activate.bat (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)
call .venv\\Scripts\\activate.bat
uvicorn {main_file}:app --reload --host 0.0.0.0 --port 8000
pause
"""
            elif "django" in backend_stack.lower():
                run_bat_content = """@echo off
echo Starting Django development server...
cd /d "%~dp0"
if not exist .venv\\Scripts\\activate.bat (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)
call .venv\\Scripts\\activate.bat
python manage.py runserver
pause
"""
            else:
                # Generic Python backend
                run_bat_content = """@echo off
echo Starting backend server...
cd /d "%~dp0"
if not exist .venv\\Scripts\\activate.bat (
    echo Virtual environment not found. Please run setup.bat first.
    pause
    exit /b 1
)
call .venv\\Scripts\\activate.bat
python -m app.main
pause
"""
            
            run_bat.write_text(run_bat_content, encoding='utf-8')
            self.logger.log("✅ Created run.bat")
        
        # Create migrate.bat for database migrations (if applicable)
        migrate_bat = backend_dir / "migrate.bat"
        if not migrate_bat.exists() and ("fastapi" in backend_stack.lower() or "django" in backend_stack.lower()):
            if "django" in backend_stack.lower():
                migrate_content = """@echo off
echo Running database migrations...
cd /d "%~dp0"
call .venv\\Scripts\\activate.bat
python manage.py makemigrations
python manage.py migrate
echo Migrations complete!
pause
"""
            else:
                # FastAPI - Alembic migrations
                migrate_content = """@echo off
echo Running database migrations...
cd /d "%~dp0"
call .venv\\Scripts\\activate.bat
alembic upgrade head
echo Migrations complete!
pause
"""
            migrate_bat.write_text(migrate_content, encoding='utf-8')
            self.logger.log("✅ Created migrate.bat")
        
        if not existing_bat_files:
            self.logger.log("✅ Created mandatory .bat files for Windows setup and execution")

    
    def _init_git(self, project_path: Path):
        """Initialize git repository"""
        try:
            import subprocess
            subprocess.run(["git", "init"], cwd=project_path, check=True, capture_output=True)
            self.logger.log("✅ Initialized git repository")
        except Exception as e:
            self.logger.log(f"⚠️ Could not initialize git: {str(e)}", level="error")

