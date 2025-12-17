"""
Package Validator - Validates and fixes package names and versions in dependency files
"""

from typing import Dict
import re
import json
from utils.code_fixer import unescape_content


class PackageValidator:
    """Validates and fixes package dependencies in requirements.txt and package.json"""
    
    def __init__(self, logger=None):
        """
        Initialize the package validator.
        
        Args:
            logger: Optional logger instance
        """
        self.logger = logger
    
    def log(self, message: str, level: str = "info"):
        """Log a message if logger is available"""
        if self.logger:
            if level == "error":
                self.logger.log(message, level="error")
            elif level == "warning":
                self.logger.log(message, level="warning")
            else:
                self.logger.log(message)
    
    @staticmethod
    def _unescape_content(content: str) -> str:
        """Unescape escape sequences in content - delegates to shared utility"""
        return unescape_content(content)
    
    def fix_python_packages(self, files: Dict[str, str]) -> Dict[str, str]:
        """
        Fix common package name mistakes in requirements.txt files.
        
        Common fixes:
        - dotenv -> python-dotenv
        - pydantic 1.x -> pydantic >=2.7.4 (for langchain compatibility)
        
        Args:
            files: Dictionary mapping file paths to file contents
            
        Returns:
            Dictionary with fixed file contents
        """
        fixed_files = files.copy()
        
        # Fix requirements.txt if it exists
        for file_path, content in fixed_files.items():
            if "requirements.txt" in file_path.lower() or file_path.endswith("requirements.txt"):
                fixed_content = content
                
                # First, ensure newlines are properly handled (unescape \n)
                fixed_content = self._unescape_content(fixed_content)
                
                # Fix dotenv -> python-dotenv (common mistake)
                # Replace dotenv==version with python-dotenv>=version
                fixed_content = re.sub(
                    r'^dotenv==([^\s]+)',
                    r'python-dotenv>=\1',
                    fixed_content,
                    flags=re.MULTILINE
                )
                # Replace dotenv>=version with python-dotenv>=version
                fixed_content = re.sub(
                    r'^dotenv>=([^\s]+)',
                    r'python-dotenv>=\1',
                    fixed_content,
                    flags=re.MULTILINE
                )
                # Replace standalone dotenv with python-dotenv (if not already python-dotenv)
                if "dotenv" in fixed_content and "python-dotenv" not in fixed_content:
                    fixed_content = re.sub(
                        r'^dotenv\s*$',
                        'python-dotenv>=1.0.0',
                        fixed_content,
                        flags=re.MULTILINE
                    )
                
                # Fix pydantic version - must be >=2.7.4 for langchain compatibility
                # Replace pydantic 1.x with pydantic 2.x
                fixed_content = re.sub(
                    r'^pydantic==1\.',
                    'pydantic>=2.7.4',
                    fixed_content,
                    flags=re.MULTILINE
                )
                fixed_content = re.sub(
                    r'^pydantic>=1\.',
                    'pydantic>=2.7.4',
                    fixed_content,
                    flags=re.MULTILINE
                )
                # If pydantic is specified but version is too old
                if re.search(r'^pydantic[<>=!]+.*1\.', fixed_content, re.MULTILINE):
                    fixed_content = re.sub(
                        r'^pydantic[<>=!]+.*1\.\d+',
                        'pydantic>=2.7.4',
                        fixed_content,
                        flags=re.MULTILINE
                    )
                    self.log("🔧 Fixed pydantic version (1.x -> 2.7.4+) in requirements.txt")
                
                fixed_files[file_path] = fixed_content
                if fixed_content != content:
                    self.log("🔧 Fixed package name/version in requirements.txt")
        
        return fixed_files
    
    def fix_frontend_packages(self, files: Dict[str, str]) -> Dict[str, str]:
        """
        Fix common package version conflicts in package.json files.
        
        Common fixes:
        - vite 2.x -> vite ^5.0.0
        - @vitejs/plugin-react version compatibility with vite 5
        
        Args:
            files: Dictionary mapping file paths to file contents
            
        Returns:
            Dictionary with fixed file contents
        """
        fixed_files = files.copy()
        
        # Fix package.json if it exists
        for file_path, content in fixed_files.items():
            if "package.json" in file_path.lower() and file_path.endswith("package.json"):
                fixed_content = self._unescape_content(content)
                
                # Fix Vite version conflicts
                try:
                    # Try to parse as JSON to fix version conflicts
                    pkg_data = json.loads(fixed_content)
                    
                    if "dependencies" in pkg_data or "devDependencies" in pkg_data:
                        deps = pkg_data.get("dependencies", {})
                        dev_deps = pkg_data.get("devDependencies", {})
                        
                        # Fix vite version if it's too old
                        if "vite" in deps:
                            vite_version = deps["vite"]
                            # If vite is version 2.x, upgrade to 5.x
                            if vite_version.startswith("^2.") or vite_version.startswith("2."):
                                deps["vite"] = "^5.0.0"
                                self.log("🔧 Fixed vite version (2.x -> 5.x) in package.json")
                        
                        if "vite" in dev_deps:
                            vite_version = dev_deps["vite"]
                            if vite_version.startswith("^2.") or vite_version.startswith("2."):
                                dev_deps["vite"] = "^5.0.0"
                                self.log("🔧 Fixed vite version (2.x -> 5.x) in package.json")
                        
                        # Ensure @vitejs/plugin-react is compatible with vite 5
                        if "@vitejs/plugin-react" in dev_deps and "vite" in (deps if "vite" in deps else dev_deps):
                            # Update plugin-react to version compatible with vite 5
                            dev_deps["@vitejs/plugin-react"] = "^4.0.0"
                            self.log("🔧 Updated @vitejs/plugin-react to version 4.x for vite 5 compatibility")
                        
                        # Update package.json with fixed dependencies
                        pkg_data["dependencies"] = deps
                        pkg_data["devDependencies"] = dev_deps
                        fixed_content = json.dumps(pkg_data, indent=2)
                        
                except json.JSONDecodeError:
                    # If JSON parsing fails, try regex-based fixes
                    # Fix vite version in package.json string
                    fixed_content = re.sub(
                        r'"vite"\s*:\s*"[\^~]?2\.',
                        '"vite": "^5.',
                        fixed_content
                    )
                    if fixed_content != self._unescape_content(content):
                        self.log("🔧 Fixed vite version using regex in package.json")
                
                fixed_files[file_path] = fixed_content
                if fixed_content != self._unescape_content(content):
                    self.log("🔧 Fixed package version conflicts in package.json")
        
        return fixed_files
    
    def fix_all_packages(self, files: Dict[str, str]) -> Dict[str, str]:
        """
        Fix both Python and frontend packages in the provided files.
        
        Args:
            files: Dictionary mapping file paths to file contents
            
        Returns:
            Dictionary with fixed file contents
        """
        fixed_files = self.fix_python_packages(files)
        fixed_files = self.fix_frontend_packages(fixed_files)
        return fixed_files

