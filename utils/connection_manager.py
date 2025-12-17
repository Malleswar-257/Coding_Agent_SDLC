"""
Connection Manager - Manages frontend-backend API connections, endpoints, and CRUD operations
"""

import ast
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from utils.logger import StreamlitLogger


class ConnectionManager:
    """Manages connections between frontend and backend"""
    
    def __init__(self, logger: Optional[StreamlitLogger] = None):
        self.logger = logger or StreamlitLogger()
    
    def setup_connections(
        self,
        project_path: Path,
        backend_code: Dict[str, str],
        project_spec: Dict[str, Any],
        frontend_stack: str = "react"
    ) -> Dict[str, Any]:
        """
        Main method to set up all frontend-backend connections
        
        Args:
            project_path: Path to the project directory
            backend_code: Dictionary of backend file paths and contents
            project_spec: Project specification with API endpoints
            frontend_stack: Frontend framework (react, vue, nextjs, svelte)
        
        Returns:
            Dictionary with connection setup results
        """
        self.logger.log("🔗 Setting up frontend-backend connections...")
        
        frontend_dir = project_path / "frontend"
        backend_dir = project_path / "backend"
        
        if not frontend_dir.exists():
            self.logger.log("⚠️ Frontend directory not found, skipping connection setup", level="warning")
            return {"success": False, "reason": "Frontend directory not found"}
        
        if not backend_dir.exists():
            self.logger.log("⚠️ Backend directory not found, skipping connection setup", level="warning")
            return {"success": False, "reason": "Backend directory not found"}
        
        # Step 1: Extract endpoints from backend code
        endpoints = self._extract_backend_endpoints(backend_dir, backend_code)
        self.logger.log(f"📡 Found {len(endpoints)} API endpoints in backend")
        
        # Step 2: Detect frontend framework and TypeScript usage
        detected_framework = self._detect_frontend_framework(frontend_dir)
        if detected_framework:
            frontend_stack = detected_framework
        use_typescript = self._detect_typescript(frontend_dir)
        self.logger.log(f"🎨 Detected frontend framework: {frontend_stack} (TypeScript={use_typescript})")
        
        # Step 3: Ensure axios is installed in frontend
        self._ensure_axios_installed(frontend_dir)
        
        # Step 4: Create API service files
        api_service_files = self._create_api_services(
            frontend_dir, endpoints, frontend_stack, project_spec, use_typescript
        )
        
        # Step 5: Update frontend components to use API services
        updated_components = self._update_frontend_components(
            frontend_dir, api_service_files, frontend_stack
        )
        
        # Step 6: Ensure backend CORS configuration
        self._ensure_backend_cors_config(backend_dir)
        
        # Step 7: Create connection documentation
        self._create_connection_docs(project_path, endpoints, api_service_files)
        
        self.logger.log("✅ Frontend-backend connections setup completed")
        
        return {
            "success": True,
            "endpoints": len(endpoints),
            "api_services": len(api_service_files),
            "updated_components": updated_components,
            "framework": frontend_stack
        }
    
    def _extract_backend_endpoints(
        self, backend_dir: Path, backend_code: Dict[str, str]
    ) -> List[Dict[str, Any]]:
        """Extract API endpoints from backend code"""
        endpoints = []
        
        # Look for route files (routes.py, routers.py, main.py, etc.)
        route_patterns = [
            "**/routes.py",
            "**/routers.py",
            "**/main.py",
            "**/api.py",
            "**/endpoints.py"
        ]
        
        route_files = []
        for pattern in route_patterns:
            route_files.extend(backend_dir.glob(pattern))
        
        # Also check backend_code dictionary
        for file_path, content in backend_code.items():
            if any(keyword in file_path.lower() for keyword in ["route", "api", "main"]):
                if file_path.endswith(".py"):
                    route_files.append(backend_dir / file_path)
        
        # Extract endpoints from each route file
        for route_file in route_files:
            if route_file.exists():
                try:
                    content = route_file.read_text(encoding="utf-8")
                    file_endpoints = self._parse_fastapi_routes(content, str(route_file))
                    endpoints.extend(file_endpoints)
                except Exception as e:
                    self.logger.log(f"⚠️ Error reading {route_file}: {str(e)}", level="warning")
        
        # Remove duplicates
        seen = set()
        unique_endpoints = []
        for ep in endpoints:
            key = (ep.get("method", ""), ep.get("path", ""))
            if key not in seen:
                seen.add(key)
                unique_endpoints.append(ep)
        
        return unique_endpoints
    
    def _parse_fastapi_routes(self, code: str, file_path: str) -> List[Dict[str, Any]]:
        """Parse FastAPI route decorators to extract endpoints (AST-based with regex fallback)"""
        endpoints: List[Dict[str, Any]] = []
        
        try:
            tree = ast.parse(code)
            router_prefixes = self._get_router_prefixes(tree)
            allowed_methods = {"get", "post", "put", "delete", "patch"}
            
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef):
                    func_name = node.name
                    params = ", ".join(arg.arg for arg in node.args.args)
                    
                    for dec in node.decorator_list:
                        if isinstance(dec, ast.Call) and isinstance(dec.func, ast.Attribute):
                            method_raw = dec.func.attr.lower()
                            if method_raw not in allowed_methods:
                                continue
                            
                            path = None
                            if dec.args and isinstance(dec.args[0], ast.Constant) and isinstance(dec.args[0].value, str):
                                path = dec.args[0].value
                            if path is None:
                                for kw in dec.keywords:
                                    if kw.arg in ("path", "url") and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                        path = kw.value.value
                                        break
                            if not path:
                                continue
                            
                            prefix = ""
                            if isinstance(dec.func.value, ast.Name):
                                prefix = router_prefixes.get(dec.func.value.id, "")
                            elif isinstance(dec.func.value, ast.Attribute) and isinstance(dec.func.value.value, ast.Name):
                                prefix = router_prefixes.get(dec.func.value.value.id, "")
                            
                            full_path = self._join_paths(prefix, path)
                            method = method_raw.upper()
                            operation_type = self._infer_operation_type(func_name, full_path, method)
                            
                            endpoints.append({
                                "method": method,
                                "path": full_path,
                                "function": func_name,
                                "file": file_path,
                                "operation": operation_type,
                                "params": params
                            })
        except SyntaxError:
            # Fallback to regex if AST fails
            route_pattern = r'@(?:app|router)\.(get|post|put|delete|patch)\s*\(\s*["\']([^"\']+)["\']'
            matches = re.finditer(route_pattern, code, re.MULTILINE)
            
            for match in matches:
                method = match.group(1).upper()
                path = match.group(2)
                func_match = re.search(
                    r'def\s+(\w+)\s*\(([^)]*)\)',
                    code[match.end():match.end() + 500]
                )
                func_name = func_match.group(1) if func_match else "unknown"
                params = func_match.group(2) if func_match else ""
                operation_type = self._infer_operation_type(func_name, path, method)
                endpoints.append({
                    "method": method,
                    "path": path,
                    "function": func_name,
                    "file": file_path,
                    "operation": operation_type,
                    "params": params
                })
        except Exception as e:
            self.logger.log(f"⚠️ Route parsing error in {file_path}: {str(e)}", level="warning")
        
        return endpoints
    
    def _get_router_prefixes(self, tree: ast.AST) -> Dict[str, str]:
        """Extract APIRouter prefixes to build full paths"""
        prefixes: Dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.Assign) and len(node.targets) == 1:
                target = node.targets[0]
                if isinstance(target, ast.Name) and isinstance(node.value, ast.Call):
                    func = node.value.func
                    func_name = func.id if isinstance(func, ast.Name) else func.attr if isinstance(func, ast.Attribute) else ""
                    if func_name == "APIRouter":
                        prefix_val = ""
                        if node.value.args and isinstance(node.value.args[0], ast.Constant) and isinstance(node.value.args[0].value, str):
                            prefix_val = node.value.args[0].value
                        for kw in node.value.keywords:
                            if kw.arg == "prefix" and isinstance(kw.value, ast.Constant) and isinstance(kw.value.value, str):
                                prefix_val = kw.value.value
                        if prefix_val:
                            prefixes[target.id] = prefix_val
        return prefixes
    
    def _join_paths(self, prefix: str, path: str) -> str:
        """Join router prefix and path safely"""
        if not prefix:
            return path
        return "/" + "/".join(
            segment for segment in f"{prefix}/{path}".split("/") if segment
        )
    
    def _infer_operation_type(self, func_name: str, path: str, method: str) -> str:
        """Infer CRUD operation type from function name, path, and method"""
        func_lower = func_name.lower()
        path_lower = path.lower()
        
        if method == "GET":
            if "list" in func_lower or "all" in func_lower or "get_all" in func_lower:
                return "READ_ALL"
            elif "get" in func_lower or "read" in func_lower or "fetch" in func_lower:
                return "READ_ONE"
            else:
                return "READ"
        elif method == "POST":
            if "create" in func_lower or "add" in func_lower or "new" in func_lower:
                return "CREATE"
            else:
                return "CREATE"
        elif method == "PUT":
            if "update" in func_lower or "edit" in func_lower or "modify" in func_lower:
                return "UPDATE"
            else:
                return "UPDATE"
        elif method == "PATCH":
            return "UPDATE_PARTIAL"
        elif method == "DELETE":
            if "delete" in func_lower or "remove" in func_lower:
                return "DELETE"
            else:
                return "DELETE"
        
        return "UNKNOWN"
    
    def _ensure_axios_installed(self, frontend_dir: Path):
        """Ensure axios is installed in frontend package.json"""
        package_json = frontend_dir / "package.json"
        if not package_json.exists():
            return
        
        try:
            with open(package_json, "r", encoding="utf-8") as f:
                pkg = json.load(f)
            
            deps = pkg.get("dependencies", {})
            dev_deps = pkg.get("devDependencies", {})
            
            # Check if axios is already installed
            if "axios" not in deps and "axios" not in dev_deps:
                # Add axios to dependencies
                if "dependencies" not in pkg:
                    pkg["dependencies"] = {}
                pkg["dependencies"]["axios"] = "^1.6.0"
                
                # Write back to file
                with open(package_json, "w", encoding="utf-8") as f:
                    json.dump(pkg, f, indent=2)
                
                self.logger.log("✅ Added axios to frontend dependencies")
        except Exception as e:
            self.logger.log(f"⚠️ Error ensuring axios installation: {str(e)}", level="warning")
    
    def _detect_frontend_framework(self, frontend_dir: Path) -> Optional[str]:
        """Detect frontend framework from project structure"""
        # Check for package.json
        package_json = frontend_dir / "package.json"
        if package_json.exists():
            try:
                with open(package_json, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    
                    if "next" in deps:
                        return "nextjs"
                    elif "react" in deps:
                        return "react"
                    elif "vue" in deps:
                        return "vue"
                    elif "svelte" in deps or "sveltekit" in deps:
                        return "svelte"
            except Exception:
                pass
        
        # Check for framework-specific files
        if (frontend_dir / "next.config.js").exists() or (frontend_dir / "next.config.ts").exists():
            return "nextjs"
        elif (frontend_dir / "vite.config.js").exists() or (frontend_dir / "vite.config.ts").exists():
            # Could be React or Vue
            if (frontend_dir / "src" / "App.vue").exists():
                return "vue"
            else:
                return "react"
        elif (frontend_dir / "svelte.config.js").exists():
            return "svelte"
        
        return None
    
    def _detect_typescript(self, frontend_dir: Path) -> bool:
        """Detect if the frontend uses TypeScript"""
        if (frontend_dir / "tsconfig.json").exists() or (frontend_dir / "tsconfig.app.json").exists():
            return True
        
        package_json = frontend_dir / "package.json"
        if package_json.exists():
            try:
                with open(package_json, "r", encoding="utf-8") as f:
                    pkg = json.load(f)
                    deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
                    if "typescript" in deps:
                        return True
            except Exception:
                pass
        
        # Look for TS/TSX files
        ts_files = list(frontend_dir.glob("**/*.ts")) + list(frontend_dir.glob("**/*.tsx"))
        return len(ts_files) > 0
    
    def _create_api_services(
        self,
        frontend_dir: Path,
        endpoints: List[Dict[str, Any]],
        framework: str,
        project_spec: Dict[str, Any],
        use_typescript: bool
    ) -> Dict[str, str]:
        """Create API service files for the frontend"""
        api_service_files = {}
        
        # Group endpoints by resource/entity
        grouped_endpoints = self._group_endpoints_by_resource(endpoints)
        
        # Create base API client
        extension = "ts" if use_typescript else "js"
        base_client = self._generate_base_api_client(framework, use_typescript)
        api_service_files[f"api/client.{extension}"] = base_client
        
        # Create service files for each resource
        for resource, resource_endpoints in grouped_endpoints.items():
            service_code = self._generate_resource_service(
                resource, resource_endpoints, framework, use_typescript
            )
            service_path = f"api/services/{resource}_service.{extension}"
            api_service_files[service_path] = service_code
        
        # Write all service files
        for file_path, content in api_service_files.items():
            full_path = frontend_dir / file_path
            full_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                full_path.write_text(content, encoding="utf-8")
                self.logger.log(f"✅ Created API service: {file_path}")
            except Exception as e:
                self.logger.log(f"⚠️ Error creating {file_path}: {str(e)}", level="warning")
        
        return api_service_files
    
    def _group_endpoints_by_resource(
        self, endpoints: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group endpoints by resource/entity name"""
        grouped = {}
        
        for endpoint in endpoints:
            path = endpoint.get("path", "")
            # Extract resource name from path (e.g., /api/users -> users)
            parts = [p for p in path.split("/") if p and p != "api"]
            resource = parts[0] if parts else "default"
            
            # Clean resource name (remove {id}, etc.)
            resource = re.sub(r'[{}]', '', resource).lower()
            
            if resource not in grouped:
                grouped[resource] = []
            grouped[resource].append(endpoint)
        
        return grouped
    
    def _generate_base_api_client(self, framework: str, use_typescript: bool) -> str:
        """Generate base API client with axios and normalized responses"""
        if framework == "nextjs":
            if use_typescript:
                return """// Base API Client for Next.js (TypeScript)
import axios, { AxiosError, AxiosResponse } from 'axios';

export interface ApiResponse<T = any> {
  data: T;
  status: number;
  message?: string;
}

export interface ApiError {
  status: number;
  message: string;
  data?: any;
}

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.API_BASE_URL ||
  'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout: 15000,
});

const normalizeResponse = <T>(response: AxiosResponse<T>): ApiResponse<T> => ({
  data: response?.data,
  status: response?.status ?? 200,
  message: (response?.data as any)?.message || response?.statusText || '',
});

const normalizeError = (error: AxiosError): ApiError => ({
  status: error?.response?.status ?? 0,
  message: (error?.response?.data as any)?.message || error?.message || 'Request failed',
  data: error?.response?.data,
});

apiClient.interceptors.request.use(
  (config) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(normalizeError(error))
);

apiClient.interceptors.response.use(
  (response) => normalizeResponse(response),
  (error) => Promise.reject(normalizeError(error))
);

export default apiClient;
"""
            else:
                return """// Base API Client for Next.js
import axios from 'axios';

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.API_BASE_URL ||
  'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout: 15000,
});

const normalizeResponse = (response) => ({
  data: response?.data,
  status: response?.status ?? 200,
  message: response?.data?.message || response?.statusText || '',
});

const normalizeError = (error) => ({
  status: error?.response?.status ?? 0,
  message: error?.response?.data?.message || error?.message || 'Request failed',
  data: error?.response?.data,
});

apiClient.interceptors.request.use(
  (config) => {
    const token = typeof window !== 'undefined' ? localStorage.getItem('token') : null;
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(normalizeError(error))
);

apiClient.interceptors.response.use(
  (response) => normalizeResponse(response),
  (error) => Promise.reject(normalizeError(error))
);

export default apiClient;
"""
        elif framework == "vue":
            if use_typescript:
                return """// Base API Client for Vue (TypeScript)
import axios, { AxiosError, AxiosResponse } from 'axios';

export interface ApiResponse<T = any> {
  data: T;
  status: number;
  message?: string;
}

export interface ApiError {
  status: number;
  message: string;
  data?: any;
}

const API_BASE_URL =
  (import.meta as any)?.env?.VITE_API_BASE_URL ||
  (import.meta as any)?.env?.API_BASE_URL ||
  'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout: 15000,
});

const normalizeResponse = <T>(response: AxiosResponse<T>): ApiResponse<T> => ({
  data: response?.data,
  status: response?.status ?? 200,
  message: (response?.data as any)?.message || response?.statusText || '',
});

const normalizeError = (error: AxiosError): ApiError => ({
  status: error?.response?.status ?? 0,
  message: (error?.response?.data as any)?.message || error?.message || 'Request failed',
  data: error?.response?.data,
});

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(normalizeError(error))
);

apiClient.interceptors.response.use(
  (response) => normalizeResponse(response),
  (error) => Promise.reject(normalizeError(error))
);

export default apiClient;
"""
            else:
                return """// Base API Client for Vue
import axios from 'axios';

const API_BASE_URL =
  (import.meta?.env?.VITE_API_BASE_URL) ||
  (import.meta?.env?.API_BASE_URL) ||
  'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout: 15000,
});

const normalizeResponse = (response) => ({
  data: response?.data,
  status: response?.status ?? 200,
  message: response?.data?.message || response?.statusText || '',
});

const normalizeError = (error) => ({
  status: error?.response?.status ?? 0,
  message: error?.response?.data?.message || error?.message || 'Request failed',
  data: error?.response?.data,
});

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(normalizeError(error))
);

apiClient.interceptors.response.use(
  (response) => normalizeResponse(response),
  (error) => Promise.reject(normalizeError(error))
);

export default apiClient;
"""
        else:  # React or default (Vite / CRA)
            if use_typescript:
                return """// Base API Client for React (TypeScript)
import axios, { AxiosError, AxiosResponse } from 'axios';

export interface ApiResponse<T = any> {
  data: T;
  status: number;
  message?: string;
}

export interface ApiError {
  status: number;
  message: string;
  data?: any;
}

const API_BASE_URL =
  (import.meta as any)?.env?.VITE_API_BASE_URL ||
  process.env.REACT_APP_API_BASE_URL ||
  process.env.API_BASE_URL ||
  'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout: 15000,
});

const normalizeResponse = <T>(response: AxiosResponse<T>): ApiResponse<T> => ({
  data: response?.data,
  status: response?.status ?? 200,
  message: (response?.data as any)?.message || response?.statusText || '',
});

const normalizeError = (error: AxiosError): ApiError => ({
  status: error?.response?.status ?? 0,
  message: (error?.response?.data as any)?.message || error?.message || 'Request failed',
  data: error?.response?.data,
});

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(normalizeError(error))
);

apiClient.interceptors.response.use(
  (response) => normalizeResponse(response),
  (error) => Promise.reject(normalizeError(error))
);

export default apiClient;
"""
            else:
                return """// Base API Client for React
import axios from 'axios';

const API_BASE_URL =
  (import.meta?.env?.VITE_API_BASE_URL) ||
  process.env.REACT_APP_API_BASE_URL ||
  process.env.API_BASE_URL ||
  'http://localhost:8000';

const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: { 'Content-Type': 'application/json' },
  withCredentials: true,
  timeout: 15000,
});

const normalizeResponse = (response) => ({
  data: response?.data,
  status: response?.status ?? 200,
  message: response?.data?.message || response?.statusText || '',
});

const normalizeError = (error) => ({
  status: error?.response?.status ?? 0,
  message: error?.response?.data?.message || error?.message || 'Request failed',
  data: error?.response?.data,
});

apiClient.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem('token');
    if (token) {
      config.headers = config.headers || {};
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(normalizeError(error))
);

apiClient.interceptors.response.use(
  (response) => normalizeResponse(response),
  (error) => Promise.reject(normalizeError(error))
);

export default apiClient;
"""
    
    def _generate_resource_service(
        self, resource: str, endpoints: List[Dict[str, Any]], framework: str, use_typescript: bool
    ) -> str:
        """Generate service file for a specific resource"""
        resource_name = resource.capitalize()
        service_name = f"{resource_name}Service"
        extension = "ts" if use_typescript else "js"
        
        methods = []
        
        for endpoint in endpoints:
            method = endpoint.get("method", "GET")
            path = endpoint.get("path", "")
            operation = endpoint.get("operation", "UNKNOWN")
            
            # Normalize id placeholder
            placeholder = "{id}" if "{id}" in path else "{item_id}" if "{item_id}" in path else "{id}"
            
            if operation == "READ_ALL":
                methods.append(f"""  // Get all {resource}
  async getAll() {{
    return apiClient.get('{path}');
  }}""")
            
            elif operation == "READ_ONE":
                methods.append(f"""  // Get {resource} by ID
  async getById(id) {{
    return apiClient.get('{path}'.replace('{placeholder}', id));
  }}""")
            
            elif operation == "CREATE":
                methods.append(f"""  // Create new {resource}
  async create(data) {{
    return apiClient.post('{path}', data);
  }}""")
            
            elif operation in ["UPDATE", "UPDATE_PARTIAL"]:
                update_method = "patch" if operation == "UPDATE_PARTIAL" else "put"
                methods.append(f"""  // Update {resource}
  async update(id, data) {{
    return apiClient.{update_method}('{path}'.replace('{placeholder}', id), data);
  }}""")
            
            elif operation == "DELETE":
                methods.append(f"""  // Delete {resource}
  async delete(id) {{
    return apiClient.delete('{path}'.replace('{placeholder}', id));
  }}""")
        
        methods_block = "\n\n".join(methods)
        
        if use_typescript:
            return f"""// {resource_name} API Service (TypeScript)
import apiClient, {{ ApiResponse, ApiError }} from '../client';

export const {service_name} = {{
{methods_block}
}};

export default {service_name};
"""
        else:
            return f"""// {resource_name} API Service
import apiClient from '../client.{extension}';

const {service_name} = {{
{methods_block}
}};

export default {service_name};
"""
    
    def _update_frontend_components(
        self,
        frontend_dir: Path,
        api_service_files: Dict[str, str],
        framework: str
    ) -> int:
        """Update frontend components to use API services"""
        updated_count = 0
        
        # Find component files
        component_patterns = {
            "react": ["**/*.jsx", "**/*.tsx", "**/components/**/*.js", "**/pages/**/*.js"],
            "nextjs": ["**/*.jsx", "**/*.tsx", "**/components/**/*.js", "**/pages/**/*.js", "**/app/**/*.js"],
            "vue": ["**/*.vue", "**/components/**/*.js"],
            "svelte": ["**/*.svelte"]
        }
        
        patterns = component_patterns.get(framework, ["**/*.jsx", "**/*.js"])
        
        components = []
        for pattern in patterns:
            components.extend(frontend_dir.glob(pattern))
        
        # Limit to reasonable number of components to update
        components = components[:20]  # Don't update too many at once
        
        for component_file in components:
            try:
                content = component_file.read_text(encoding="utf-8")
                
                # Check if component has hardcoded API calls that should use services
                if self._has_hardcoded_api_calls(content):
                    updated_content = self._inject_api_service_imports(content, api_service_files)
                    if updated_content != content:
                        component_file.write_text(updated_content, encoding="utf-8")
                        updated_count += 1
                        self.logger.log(f"✅ Updated component: {component_file.name}")
            except Exception as e:
                self.logger.log(f"⚠️ Error updating {component_file}: {str(e)}", level="warning")
        
        return updated_count
    
    def _has_hardcoded_api_calls(self, content: str) -> bool:
        """Check if component has hardcoded fetch/axios calls"""
        patterns = [
            r'fetch\s*\(["\']http',
            r'axios\.(get|post|put|delete|patch)\s*\(',
            r'http://localhost:8000',
            r'http://127\.0\.0\.1:8000'
        ]
        
        for pattern in patterns:
            if re.search(pattern, content, re.IGNORECASE):
                return True
        
        return False
    
    def _inject_api_service_imports(
        self, content: str, api_service_files: Dict[str, str]
    ) -> str:
        """Inject API service imports into component"""
        # Find available services
        services = []
        extension = "js"
        for file_path in api_service_files.keys():
            if "services" in file_path:
                ext = file_path.split(".")[-1]
                extension = ext
                resource = file_path.split("/")[-1].replace(f"_service.{ext}", "")
                services.append(resource)
        
        # Add import statement if not present
        import_pattern = r'import\s+.*from\s+["\']\.\.?/api'
        if not re.search(import_pattern, content):
            # Add import at the top after other imports
            import_section = self._find_import_section(content)
            if import_section:
                # Add example import for first service
                if services:
                    example_import = f"import {services[0].capitalize()}Service from '../api/services/{services[0]}_service.{extension}';\n"
                    content = content[:import_section] + example_import + content[import_section:]
        
        return content
    
    def _find_import_section(self, content: str) -> int:
        """Find the end of import section"""
        lines = content.split('\n')
        for i, line in enumerate(lines):
            stripped = line.strip()
            if stripped and not stripped.startswith('import') and not stripped.startswith('//') and not stripped.startswith('/*'):
                return content.find('\n', content.find(lines[i-1])) if i > 0 else 0
        return len(content)
    
    def _ensure_backend_cors_config(self, backend_dir: Path):
        """Ensure backend has proper CORS configuration"""
        main_files = [
            backend_dir / "app" / "main.py",
            backend_dir / "main.py",
            backend_dir / "backend" / "main.py"
        ]
        
        for main_file in main_files:
            if main_file.exists():
                try:
                    content = main_file.read_text(encoding="utf-8")
                    
                    # Check if CORS is already configured
                    if "CORSMiddleware" in content:
                        continue
                    
                    # Inject CORS middleware
                    cors_code = """from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
"""
                    
                    # Find where to insert (after app creation)
                    if "app = FastAPI" in content:
                        insert_pos = content.find("app = FastAPI")
                        # Find end of FastAPI() call
                        paren_count = 0
                        start_pos = insert_pos
                        for i in range(insert_pos, len(content)):
                            if content[i] == '(':
                                paren_count += 1
                            elif content[i] == ')':
                                paren_count -= 1
                                if paren_count == 0:
                                    insert_pos = i + 1
                                    break
                        
                        # Insert CORS code
                        new_content = content[:insert_pos] + "\n\n" + cors_code + content[insert_pos:]
                        main_file.write_text(new_content, encoding="utf-8")
                        self.logger.log(f"✅ Added CORS configuration to {main_file.name}")
                except Exception as e:
                    self.logger.log(f"⚠️ Error configuring CORS in {main_file}: {str(e)}", level="warning")
    
    def _create_connection_docs(
        self,
        project_path: Path,
        endpoints: List[Dict[str, Any]],
        api_service_files: Dict[str, str]
    ):
        """Create documentation for API connections"""
        docs_content = f"""# API Connection Documentation

## Overview
This document describes the API connections between frontend and backend.

## Backend Endpoints

Total endpoints: {len(endpoints)}

### Endpoints List

"""
        
        for endpoint in endpoints:
            docs_content += f"- **{endpoint.get('method', 'GET')}** `{endpoint.get('path', '/')}`\n"
            docs_content += f"  - Function: `{endpoint.get('function', 'unknown')}`\n"
            docs_content += f"  - Operation: `{endpoint.get('operation', 'UNKNOWN')}`\n\n"
        
        docs_content += f"""
## Frontend API Services

Total services: {len(api_service_files)}

### Available Services

"""
        
        for file_path in api_service_files.keys():
            if "services" in file_path:
                filename = file_path.split("/")[-1]
                resource = filename.split("_service")[0]
                docs_content += f"- `{filename}` - {resource.capitalize()} API operations\n"
        
        docs_content += """
## Usage Example

```javascript
import UserService from './api/services/user_service.js';

// Get all users
const users = await UserService.getAll();

// Get user by ID
const user = await UserService.getById(1);

// Create new user
const newUser = await UserService.create({ name: 'John', email: 'john@example.com' });

// Update user
const updated = await UserService.update(1, { name: 'Jane' });

// Delete user
await UserService.delete(1);
```

## Environment Variables

Make sure to set the following environment variables:

- `VITE_API_BASE_URL` (Vite projects)
- `NEXT_PUBLIC_API_BASE_URL` (Next.js projects)
- `REACT_APP_API_BASE_URL` (Create React App)

Default: `http://localhost:8000`
"""
        
        docs_path = project_path / "API_CONNECTIONS.md"
        try:
            docs_path.write_text(docs_content, encoding="utf-8")
            self.logger.log("✅ Created API connection documentation")
        except Exception as e:
            self.logger.log(f"⚠️ Error creating connection docs: {str(e)}", level="warning")

