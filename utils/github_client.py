"""
GitHub Client and Publisher - Unified module for GitHub operations
Consolidates GitHubClient and GitHubPublisherAgent into a single efficient module
"""

import os
import requests
import base64
from typing import Dict, Any, Optional
from pathlib import Path
import json
from urllib.parse import quote

class GitHubClient:
    """Client for interacting with GitHub API"""
    
    def __init__(self, access_token: Optional[str] = None):
        self.access_token = access_token or os.getenv("GITHUB_ACCESS_TOKEN", "")
        self.base_url = "https://api.github.com"
        # GitHub API accepts both "token" and "Bearer" formats
        # Using "token" format for personal access tokens
        self.headers = {
            "Accept": "application/vnd.github.v3+json"
        }
        if self.access_token:
            self.headers["Authorization"] = f"token {self.access_token}"
    
    def create_repository(self, repo_name: str, description: str = "", private: bool = False) -> Dict[str, Any]:
        """Create a new GitHub repository"""
        url = f"{self.base_url}/user/repos"
        data = {
            "name": repo_name,
            "description": description,
            "private": private,
            "auto_init": False
        }
        
        response = requests.post(url, headers=self.headers, json=data)
        if response.status_code == 201:
            return response.json()
        elif response.status_code == 422:
            # Repository already exists
            return {"error": "Repository already exists", "status": 422}
        else:
            response.raise_for_status()
    
    def get_file_sha(self, repo_name: str, file_path: str) -> Optional[str]:
        """Get the SHA hash of an existing file in the repository"""
        try:
            username = self.get_username()
            # URL encode the file path to handle special characters
            encoded_path = '/'.join(quote(part, safe='') for part in file_path.split('/'))
            url = f"{self.base_url}/repos/{username}/{repo_name}/contents/{encoded_path}"
            
            response = requests.get(url, headers=self.headers, timeout=10)
            if response.status_code == 200:
                return response.json().get("sha")
            elif response.status_code == 404:
                # File doesn't exist
                return None
            else:
                # Other error, return None to try upload anyway
                return None
        except Exception:
            # If we can't check, return None and try upload anyway
            return None
    
    def upload_file(self, repo_name: str, file_path: str, content: bytes, commit_message: str = "Add file", is_binary: bool = False) -> Dict[str, Any]:
        """Upload a single file to repository
        
        Args:
            repo_name: Name of the repository
            file_path: Path to file in repository
            content: File content as bytes
            commit_message: Commit message
            is_binary: Whether the file is binary (affects encoding)
        """
        username = self.get_username()
        # URL encode the file path to handle special characters
        # Use quote with safe='/' to preserve path separators
        encoded_path = '/'.join(quote(part, safe='') for part in file_path.split('/'))
        url = f"{self.base_url}/repos/{username}/{repo_name}/contents/{encoded_path}"
        
        # Check if file exists and get its SHA
        existing_sha = self.get_file_sha(repo_name, file_path)
        
        # Encode content to base64 (GitHub API requires base64)
        try:
            content_encoded = base64.b64encode(content).decode('utf-8')
        except Exception as e:
            raise ValueError(f"Failed to encode content for {file_path}: {str(e)}")
        
        data = {
            "message": commit_message,
            "content": content_encoded
        }
        
        # Include SHA if file exists (required for updates)
        if existing_sha:
            data["sha"] = existing_sha
        
        try:
            response = requests.put(url, headers=self.headers, json=data, timeout=30)
            if response.status_code in [200, 201]:
                return response.json()
            else:
                # Get detailed error message
                error_msg = f"HTTP {response.status_code}"
                try:
                    error_data = response.json()
                    error_msg = error_data.get('message', error_msg)
                    if 'errors' in error_data:
                        error_details = error_data['errors']
                        error_msg += f" - {error_details}"
                except:
                    error_msg = response.text[:200] if response.text else error_msg
                raise requests.exceptions.HTTPError(f"{error_msg} (for {file_path})", response=response)
        except requests.exceptions.RequestException as e:
            # Re-raise with more context
            raise requests.exceptions.RequestException(f"Failed to upload {file_path}: {str(e)}")
    
    def _is_binary_file(self, file_path: Path) -> bool:
        """Check if a file is binary by attempting to read it as text"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                f.read(1024)  # Read first 1KB
            return False
        except (UnicodeDecodeError, UnicodeError):
            return True
    
    def _should_skip_file(self, file_path: Path) -> bool:
        """Determine if a file should be skipped"""
        file_str = str(file_path)
        
        # Skip common directories and files
        skip_patterns = [
            '.git', '__pycache__', 'node_modules', '.env',
            '.DS_Store', 'Thumbs.db', '.pytest_cache',
            '.coverage', 'htmlcov', '.mypy_cache',
            'dist', 'build', '.next', '.nuxt', '.cache'
        ]
        
        if any(skip in file_str for skip in skip_patterns):
            return True
        
        # Skip files larger than 50MB (GitHub limit is 100MB, but we'll be conservative)
        try:
            file_size = file_path.stat().st_size
            if file_size > 50 * 1024 * 1024:  # 50MB
                return True
        except (OSError, ValueError):
            return True
        
        return False
    
    def upload_directory(self, repo_name: str, local_dir: Path, commit_message: str = "Initial commit") -> Dict[str, Any]:
        """Upload entire directory to repository"""
        results = []
        
        for file_path in local_dir.rglob("*"):
            if not file_path.is_file():
                continue
            
            # Skip certain files
            if self._should_skip_file(file_path):
                continue
            
            # Get relative path
            relative_path = file_path.relative_to(local_dir)
            github_path = str(relative_path).replace('\\', '/')
            
            try:
                # Determine if file is binary
                is_binary = self._is_binary_file(file_path)
                
                # Read file content
                if is_binary:
                    # Read binary files as bytes
                    with open(file_path, 'rb') as f:
                        content = f.read()
                else:
                    # Read text files and encode to bytes
                    try:
                        with open(file_path, 'r', encoding='utf-8') as f:
                            text_content = f.read()
                        content = text_content.encode('utf-8')
                    except UnicodeDecodeError:
                        # Fallback: try with different encoding
                        try:
                            with open(file_path, 'r', encoding='latin-1') as f:
                                text_content = f.read()
                            content = text_content.encode('utf-8')
                        except Exception:
                            # If all else fails, read as binary
                            with open(file_path, 'rb') as f:
                                content = f.read()
                            is_binary = True
                
                # Upload file
                result = self.upload_file(repo_name, github_path, content, commit_message, is_binary)
                results.append({"file": github_path, "status": "success"})
                
            except requests.exceptions.HTTPError as e:
                error_msg = str(e)
                if hasattr(e, 'response') and e.response is not None:
                    try:
                        error_data = e.response.json()
                        error_msg = error_data.get('message', str(e))
                        # Add more context if available
                        if 'errors' in error_data:
                            errors = error_data['errors']
                            if isinstance(errors, list) and len(errors) > 0:
                                error_msg += f" - {errors[0]}"
                    except:
                        if hasattr(e.response, 'text') and e.response.text:
                            error_msg = e.response.text[:200]  # First 200 chars
                results.append({"file": github_path, "status": "error", "error": error_msg})
            except Exception as e:
                error_msg = str(e)
                # Provide more context for common errors
                if "Not Found" in error_msg or "404" in error_msg:
                    error_msg = f"Repository or path not found. Check repository name and permissions. Original: {error_msg}"
                results.append({"file": github_path, "status": "error", "error": error_msg})
        
        return {"uploaded_files": results}
    
    def get_username(self) -> str:
        """Get the authenticated user's username"""
        url = f"{self.base_url}/user"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        return response.json()["login"]
    
    def repository_exists(self, repo_name: str) -> bool:
        """Check if repository exists"""
        try:
            username = self.get_username()
            url = f"{self.base_url}/repos/{username}/{repo_name}"
            response = requests.get(url, headers=self.headers)
            return response.status_code == 200
        except:
            return False
    
    def publish_project(
        self, 
        project_config: Dict[str, Any], 
        project_directory: str,
        logger: Optional[Any] = None
    ) -> Dict[str, Any]:
        """
        Publish a complete project to GitHub (high-level method).
        
        This method combines repository creation and file uploading into a single operation.
        
        Args:
            project_config: Dictionary containing project_name and description
            project_directory: Path to the project directory to upload
            logger: Optional logger instance for logging messages
            
        Returns:
            Dictionary with success status, repository URL, and upload statistics
        """
        def log(message: str, level: str = "info"):
            """Helper to log messages if logger is available"""
            if logger:
                if hasattr(logger, 'log'):
                    logger.log(message, level=level)
                else:
                    print(message)
        
        project_name = project_config["project_name"]
        description = project_config.get("description", "Generated full-stack application")
        
        log(f"📤 Publishing project to GitHub: {project_name}")
        
        try:
            # Check if GitHub token is available
            if not self.access_token:
                log("⚠️ No GitHub token found - skipping GitHub publish")
                return {
                    "success": False,
                    "error": "No GitHub access token configured",
                    "skip_reason": "no_token"
                }
            
            # Create repository
            log(f"🔨 Creating GitHub repository: {project_name}")
            repo_result = self.create_repository(
                repo_name=project_name,
                description=f"🚀 {description} | Generated with CODE AGENT",
                private=False
            )
            
            if repo_result.get("error") == "Repository already exists":
                log(f"📁 Repository {project_name} already exists - updating files")
                if not self.repository_exists(project_name):
                    raise Exception(f"Repository {project_name} exists but is not accessible. Check permissions.")
            elif "clone_url" in repo_result:
                log(f"✅ Repository created: {repo_result['html_url']}")
            else:
                if not self.repository_exists(project_name):
                    raise Exception(f"Failed to create or access repository {project_name}. Check GitHub token permissions.")
            
            # Upload project files
            log("📁 Uploading project files to GitHub...")
            project_path = Path(project_directory)
            
            if not project_path.exists():
                raise Exception(f"Project directory does not exist: {project_directory}")
            
            upload_result = self.upload_directory(
                repo_name=project_name,
                local_dir=project_path,
                commit_message="🚀 Initial commit - Generated with CODE AGENT"
            )
            
            uploaded_count = len([f for f in upload_result["uploaded_files"] if f["status"] == "success"])
            error_count = len([f for f in upload_result["uploaded_files"] if f["status"] == "error"])
            failed_files = [f for f in upload_result["uploaded_files"] if f["status"] == "error"]
            
            log(f"✅ Uploaded {uploaded_count} files to GitHub")
            if error_count > 0:
                log(f"⚠️ {error_count} files failed to upload")
                for failed_file in failed_files[:5]:
                    error_msg = failed_file.get("error", "Unknown error")
                    if len(error_msg) > 100:
                        error_msg = error_msg[:100] + "..."
                    log(f"   ❌ {failed_file['file']}: {error_msg}")
                if len(failed_files) > 5:
                    log(f"   ... and {len(failed_files) - 5} more files failed")
            
            # Get repository URL
            username = self.get_username()
            repo_url = f"https://github.com/{username}/{project_name}"
            
            return {
                "success": True,
                "repository_url": repo_url,
                "uploaded_files": uploaded_count,
                "failed_files": error_count,
                "username": username
            }
            
        except Exception as e:
            log(f"❌ Error publishing to GitHub: {str(e)}", level="error")
            return {
                "success": False,
                "error": str(e)
            }


# Backward compatibility: GitHubPublisherAgent wrapper class
class GitHubPublisherAgent:
    """
    Agent wrapper for GitHub publishing (backward compatibility).
    
    This class maintains the agent interface while delegating to GitHubClient.
    The 'llm' parameter is kept for interface compatibility but is not used.
    """
    
    def __init__(self, llm: Any, logger: Any):
        """
        Initialize the GitHub publisher agent.
        
        Args:
            llm: LLM instance (kept for interface compatibility, not used)
            logger: Logger instance for logging messages
        """
        self.llm = llm  # Not used, but kept for interface compatibility
        self.logger = logger
        self.github_client = GitHubClient()
    
    def publish(self, project_config: Dict[str, Any], project_directory: str) -> Dict[str, Any]:
        """
        Publish project to GitHub (delegates to GitHubClient.publish_project).
        
        Args:
            project_config: Dictionary containing project_name and description
            project_directory: Path to the project directory to upload
            
        Returns:
            Dictionary with success status, repository URL, and upload statistics
        """
        return self.github_client.publish_project(
            project_config=project_config,
            project_directory=project_directory,
            logger=self.logger
        )