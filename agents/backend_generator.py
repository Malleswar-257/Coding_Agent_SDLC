"""
BackendGeneratorAgent - Generates full backend (routes, models, auth, DB schema) for selected stack
"""

from typing import Dict, Any
from langchain_core.prompts import ChatPromptTemplate
import json
from utils.logger import StreamlitLogger
from utils.code_fixer import CodeFixer
from utils.content_parsers import RobustJSONParser

class BackendGeneratorAgent:
    """Agent that generates backend code"""
    
    def __init__(self, llm, logger: StreamlitLogger):
        self.llm = llm
        self.logger = logger
        self.code_fixer = CodeFixer(logger=logger)
        self.json_parser = RobustJSONParser(logger=logger, code_fixer=self.code_fixer)
    
    def generate(self, project_spec: Dict[str, Any], backend_stack: str) -> Dict[str, str]:
        """Generate backend code based on spec"""
        self.logger.log(f"🔧 Generating {backend_stack} backend code...")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert backend developer. Generate production-ready backend code that implements the project specification.

CRITICAL: You MUST return ONLY valid JSON. No markdown, no explanations, just pure JSON.

JSON FORMATTING REQUIREMENTS:
- Escape ALL quotes inside string values using \"
- Escape ALL newlines inside string values using \\n (not literal newlines)
- Escape ALL backslashes using \\
- Ensure ALL strings are properly closed with closing quotes
- Do NOT include literal newlines in JSON string values - use \\n instead
- Test that your JSON is valid before returning it

Requirements:
1. Implement all API endpoints from the specification
2. Create database models matching the schema
3. Add authentication/authorization if required
4. Include proper error handling and validation
5. Add environment variable configuration
6. Include database migrations if applicable
7. Add proper project structure
8. Include tests (unit/integration)

CRITICAL CODE QUALITY REQUIREMENTS:
- Use consistent 4-space indentation for Python code (NO tabs, NO mixed indentation)
- Ensure all functions, classes, and code blocks are COMPLETE (no truncated code)
- Close all brackets, braces, and parentheses properly
- Include proper docstrings and type hints where applicable
- All code must be syntactically valid and runnable
- Do NOT truncate code - generate complete implementations

CRITICAL PACKAGE NAME AND VERSION REQUIREMENTS:
- Use "python-dotenv" NOT "dotenv" for environment variables
- Use "pydantic>=2.7.4" NOT "pydantic<2.0.0" (required for langchain compatibility)
- Use valid, existing package names and versions
- Common packages with compatible versions:
  * fastapi>=0.104.0
  * uvicorn>=0.24.0
  * sqlalchemy>=2.0.0
  * pydantic>=2.7.4 (CRITICAL: Must be 2.x for langchain compatibility)
  * python-dotenv>=1.0.0
  * python-jose>=3.3.0
  * passlib>=1.7.4
  * bcrypt>=4.0.0
- Always use real package versions that exist on PyPI

Return ONLY a valid JSON object with file paths as keys and file contents as values. 
CRITICAL: Escape all quotes, newlines, and special characters properly:
- Use \\" for quotes inside strings
- Use \\n for newlines (NOT literal newlines)
- Use \\\\ for backslashes
- Ensure every string starts with " and ends with "

Example format:
{{
    "requirements.txt": "fastapi==0.104.1\\nuvicorn==0.24.0\\npython-dotenv>=1.0.0",
    "app/main.py": "from fastapi import FastAPI\\nfrom dotenv import load_dotenv\\n\\nload_dotenv()\\napp = FastAPI()",
    "app/models.py": "from sqlalchemy import Column, Integer, String",
    ...
}}

IMPORTANT: Your JSON must be parseable by json.loads() - validate it before returning!

Include ALL necessary files for a complete backend application:
- Main application file
- Models/schemas
- Routes/controllers
- Authentication middleware
- Database configuration
- Environment configuration (.env.example with default values)
- Settings/config files MUST provide default values for all environment variables
- Use pydantic BaseSettings (pydantic>=2.7.4) with default values, not required fields
- Example Settings class:
  ```python
  from pydantic_settings import BaseSettings
  
  class Settings(BaseSettings):
      DATABASE_URL: str = "sqlite:///./app.db"
      SECRET_KEY: str = "dev-secret-key-change-in-production"
      # All fields should have defaults
  ```
- NEVER use required fields without defaults in Settings classes
- Requirements/dependencies file
- README.md with setup instructions
- Docker configuration if applicable

MANDATORY: You MUST include Windows batch files (.bat) for setup and running:
- setup.bat: Installs dependencies (pip install -r requirements.txt)
- run.bat: Starts the development server
- For FastAPI: run.bat should execute "uvicorn app.main:app --reload"
- For Django: run.bat should execute "python manage.py runserver"
- Additional .bat files for common tasks (migrate.bat, test.bat, etc.) if applicable

Example .bat file format:
```batch
@echo off
echo Starting application...
cd /d "%~dp0"
pip install -r requirements.txt
uvicorn app.main:app --reload
pause
```

IMPORTANT: Return ONLY the JSON object, no markdown code blocks, no explanations."""),
            ("human", """Project Specification:
{project_spec}

Backend Stack: {backend_stack}

{endpoints_section}

CRITICAL REQUIREMENTS FOR API ENDPOINTS:
- You MUST implement ALL endpoints from the api_endpoints array below
- Use the EXACT path, method, and request_body fields as specified for each endpoint
- Do NOT modify, change, or skip any endpoints
- Do NOT change endpoint paths, methods, or input field names/types
- Copy the endpoints exactly as provided in the specification
- Ensure ALL input fields from request_body are included in the endpoint implementation
- Create Pydantic models/schemas for request bodies using the exact field names and types
- Implement route handlers that accept these exact input fields

Generate complete backend code implementing ALL requirements using the exact endpoints from the specification.""")
        ])
        
        # Display API endpoints that will be used and prepare endpoints section for prompt
        api_endpoints = project_spec.get("api_endpoints", [])
        endpoints_section = ""
        
        if api_endpoints:
            self.logger.log(f"📋 Implementing {len(api_endpoints)} API endpoints from impact analysis:")
            for idx, endpoint in enumerate(api_endpoints, 1):
                method = endpoint.get("method", "GET")
                path = endpoint.get("path", "")
                request_body = endpoint.get("request_body", {})
                description = endpoint.get("description", "")
                
                log_line = f"  {idx}. {method} {path}"
                if request_body:
                    fields_str = ", ".join([f"{k}: {v}" for k, v in request_body.items()])
                    log_line += f" - Input Fields: [{fields_str}]"
                else:
                    log_line += " - Input Fields: (none)"
                if description:
                    log_line += f" - {description}"
                self.logger.log(log_line)
            
            # Create detailed endpoints section for the prompt
            endpoints_json = json.dumps(api_endpoints, indent=2)
            endpoints_section = f"""EXACT API ENDPOINTS TO IMPLEMENT (from Impact Analysis):
{endpoints_json}

CRITICAL: You MUST implement ALL {len(api_endpoints)} endpoints listed above. Each endpoint must:
1. Use the exact path and method specified
2. Include ALL input fields from request_body in the endpoint handler
3. Create Pydantic schemas/models with the exact field names and types
4. Implement the endpoint logic to handle these input fields"""
        else:
            endpoints_section = "Note: No specific endpoints provided - generate based on project specification."
        
        # Retry logic to ensure we get LLM-generated code
        max_retries = 3
        for attempt in range(max_retries):
            try:
                messages = prompt.format_messages(
                    project_spec=json.dumps(project_spec, indent=2),
                    backend_stack=backend_stack,
                    endpoints_section=endpoints_section
                )
                
                self.logger.log(f"🤖 Calling LLM to generate backend code (attempt {attempt + 1}/{max_retries})...")
                response = self.llm.invoke(messages)
                content = response.content.strip()
                
                # Parse JSON from response using the robust JSON parser
                backend_code = self.json_parser.parse(content, extract_first=True)
                
                # Post-process: fix code formatting and validate completeness
                backend_code = self.code_fixer.format_code_files(backend_code)
                
                # Validate we got actual code files
                if not isinstance(backend_code, dict) or len(backend_code) < 3:
                    raise ValueError("LLM response doesn't contain enough files")
                
                # Validate file completeness
                self._validate_file_completeness(backend_code)
                
                file_count = len(backend_code)
                self.logger.log(f"✅ Generated {file_count} backend files from LLM")
                
                return backend_code
                
            except json.JSONDecodeError as e:
                self.logger.log(f"⚠️ JSON parse error (attempt {attempt + 1}/{max_retries}): {str(e)}")
                if attempt < max_retries - 1:
                    # Ask LLM to fix the JSON
                    fix_prompt = f"""The previous response had invalid JSON. Please fix it and return ONLY valid JSON.

Previous response (first 500 chars):
{content[:500]}

Error: {str(e)}

Return ONLY the corrected JSON object:"""
                    try:
                        fix_response = self.llm.invoke([("user", fix_prompt)])
                        content = fix_response.content.strip()
                        # Try parsing again using the JSON parser
                        backend_code = self.json_parser.parse(content, extract_first=True)
                        if isinstance(backend_code, dict) and len(backend_code) >= 3:
                            self.logger.log(f"✅ Generated {len(backend_code)} backend files after JSON fix")
                            return backend_code
                    except:
                        continue
                else:
                    self.logger.log(f"❌ Failed to parse JSON after {max_retries} attempts", level="error")
                    
            except Exception as e:
                self.logger.log(f"⚠️ Error generating backend (attempt {attempt + 1}/{max_retries}): {str(e)}", level="error")
                if attempt == max_retries - 1:
                    self.logger.log("⚠️ Falling back to minimal backend scaffold due to LLM failures", level="error")
                    return self._fallback_backend(backend_stack, project_spec)
        
        # Final safety fallback
        return self._fallback_backend(backend_stack, project_spec)
    
    def _validate_python_syntax(self, file_path: str, code: str) -> str:
        """Validate Python syntax and fix common issues"""
        # Use CodeFixer for comprehensive fixing
        return self.code_fixer.validate_and_fix(code, file_path, max_attempts=3)
    
    def _validate_python_syntax_legacy(self, file_path: str, code: str) -> str:
        """Legacy method - delegates to CodeFixer"""
        # All fixing logic is now in CodeFixer
        return self.code_fixer.validate_and_fix(code, file_path, max_attempts=5)
    
    
    def _validate_file_completeness(self, backend_code: Dict[str, str]):
        """Validate that all generated files are complete and not empty"""
        min_file_sizes = {
            '.py': 50,  # Python files should be at least 50 chars
            '.txt': 10,
            '.md': 20,
        }
        
        for file_path, content in backend_code.items():
            if not content or len(content.strip()) == 0:
                self.logger.log(f"⚠️ Warning: {file_path} is empty", level="warning")
                continue
            
            # Check minimum size based on file extension
            for ext, min_size in min_file_sizes.items():
                if file_path.endswith(ext):
                    if len(content.strip()) < min_size:
                        self.logger.log(f"⚠️ Warning: {file_path} seems too short ({len(content)} chars), might be incomplete", level="warning")
                    break
            
            # Check for Python files that might be incomplete
            if file_path.endswith('.py'):
                # Check if file has at least one function or class
                if 'def ' not in content and 'class ' not in content:
                    # Might be a config file, but log it
                    if 'import' not in content and len(content) < 100:
                        self.logger.log(f"⚠️ Warning: {file_path} might be incomplete (no functions/classes found)", level="warning")
    
    def _fallback_backend(self, backend_stack: str, project_spec: Dict[str, Any]) -> Dict[str, str]:
        """Return a minimal backend scaffold so the pipeline can continue."""
        self.logger.log("🔧 Using fallback backend scaffold (minimal)", level="warning")
        api_note = "Generated fallback; extend endpoints per PRD/impact analysis."

        fastapi_files = {
            "backend/requirements.txt": "\n".join([
                "fastapi==0.104.1",
                "uvicorn[standard]==0.24.0",
                "pydantic>=2.7.4",
                "python-dotenv>=1.0.0",
                "sqlalchemy>=2.0.0",
            ]),
            "backend/app/main.py": "\n".join([
                "from fastapi import FastAPI",
                "from dotenv import load_dotenv",
                "import os",
                "",
                "load_dotenv()",
                "app = FastAPI(title=\"Fallback Backend\", description=\"Minimal scaffold\")",
                "",
                "@app.get('/health')",
                "def health():",
                "    return {'status': 'ok'}",
                "",
                "# TODO: Implement endpoints from PRD and impact analysis",
            ]),
            "backend/app/routers.py": "\n".join([
                "# Add your routers and endpoint implementations here",
                "# This is a fallback scaffold generated when LLM failed.",
                f"# Notes: {api_note}",
            ]),
            "backend/.env.example": "\n".join([
                "DATABASE_URL=sqlite:///./app.db",
                "SECRET_KEY=change-me",
            ]),
            "backend/README.md": "\n".join([
                "# Fallback Backend",
                "",
                f"{api_note}",
                "",
                "## Setup (Windows)",
                "Double-click `setup.bat` or run:",
                "```batch",
                "setup.bat",
                "```",
                "",
                "## Run (Windows)",
                "Double-click `run.bat` or run:",
                "```batch",
                "run.bat",
                "```",
                "",
                "## Setup (Linux/Mac)",
                "```bash",
                "python -m venv .venv",
                "source .venv/bin/activate",
                "pip install -r requirements.txt",
                "```",
                "",
                "## Run (Linux/Mac)",
                "```bash",
                "uvicorn app.main:app --reload",
                "```",
            ]),
            "backend/setup.bat": "\n".join([
                "@echo off",
                "echo Installing backend dependencies...",
                "cd /d \"%~dp0\"",
                "python -m venv .venv",
                "call .venv\\Scripts\\activate.bat",
                "pip install --upgrade pip",
                "pip install -r requirements.txt",
                "echo.",
                "echo Setup complete! Activate virtual environment with: .venv\\Scripts\\activate.bat",
                "pause"
            ]),
            "backend/run.bat": "\n".join([
                "@echo off",
                "echo Starting FastAPI server...",
                "cd /d \"%~dp0\"",
                "if not exist .venv\\Scripts\\activate.bat (",
                "    echo Virtual environment not found. Please run setup.bat first.",
                "    pause",
                "    exit /b 1",
                ")",
                "call .venv\\Scripts\\activate.bat",
                "uvicorn app.main:app --reload --host 0.0.0.0 --port 8000",
                "pause"
            ]),
        }

        if "django" in backend_stack.lower():
            django_files = {
                "backend/requirements.txt": "\n".join([
                    "Django>=5.0.0",
                    "djangorestframework>=3.15.0",
                    "python-dotenv>=1.0.0",
                ]),
                "backend/manage.py": "# Minimal placeholder - generate Django project manually if needed\n",
                "backend/README.md": "\n".join([
                    "# Fallback Django Backend",
                    f"{api_note}",
                    "Run `django-admin startproject app .` to scaffold a full project.",
                ]),
            }
            return django_files

        return fastapi_files
    

