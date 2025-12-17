"""
PackagerAgent - Creates downloadable ZIP with perfect folder structure
"""

from pathlib import Path
from typing import Optional
import tempfile
import zipfile
import shutil
from utils.logger import StreamlitLogger

class PackagerAgent:
    """Agent that packages the project into a ZIP file"""
    
    def __init__(self, llm, logger: StreamlitLogger):
        self.llm = llm
        self.logger = logger
    
    def package(self, project_path: str, project_name: str) -> str:
        """Package project into a ZIP file"""
        self.logger.log("📦 Creating project ZIP archive...")
        
        try:
            # Create ZIP file
            zip_path = Path(tempfile.gettempdir()) / f"{project_name}.zip"
            
            project_dir = Path(project_path)
            
            with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
                for file_path in project_dir.rglob('*'):
                    if file_path.is_file():
                        # Skip .git directory
                        if '.git' in file_path.parts:
                            continue
                        
                        arc_name = file_path.relative_to(project_dir)
                        zipf.write(file_path, arc_name)
            
            zip_size = zip_path.stat().st_size / (1024 * 1024)  # Size in MB
            self.logger.log(f"✅ Created ZIP archive ({zip_size:.2f} MB)")
            
            return str(zip_path)
            
        except Exception as e:
            self.logger.log(f"⚠️ Error creating ZIP: {str(e)}", level="error")
            raise

