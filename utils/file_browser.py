"""
File Browser Utility for Streamlit
Provides file tree view 
"""

from pathlib import Path
from typing import List, Optional, Dict
import streamlit as st


def get_file_icon(file_path: Path) -> str:
    """Get emoji icon for file type"""
    suffix = file_path.suffix.lower()
    
    icon_map = {
        '.py': '🐍',
        '.js': '📜',
        '.jsx': '⚛️',
        '.ts': '📘',
        '.tsx': '⚛️',
        '.html': '🌐',
        '.css': '🎨',
        '.json': '📋',
        '.md': '📝',
        '.txt': '📄',
        '.yml': '⚙️',
        '.yaml': '⚙️',
        '.toml': '⚙️',
        '.env': '🔐',
        '.gitignore': '🚫',
        '.dockerfile': '🐳',
        '.sh': '💻',
        '.bat': '💻',
        '.png': '🖼️',
        '.jpg': '🖼️',
        '.jpeg': '🖼️',
        '.svg': '🖼️',
        '.pdf': '📕',
    }
    
    return icon_map.get(suffix, '📄')


def build_file_tree(base_path: Path, max_depth: int = 10, current_depth: int = 0) -> List[Dict]:
    """Build a tree structure of files and directories"""
    tree = []
    
    if not base_path.exists() or current_depth > max_depth:
        return tree
    
    try:
        items = sorted(base_path.iterdir(), key=lambda x: (x.is_file(), x.name.lower()))
        
        for item in items:
            # Skip hidden files and common ignore patterns
            if item.name.startswith('.') and item.name != '.gitignore':
                continue
            
            if item.name in ['__pycache__', 'node_modules', '.git', '.venv', 'venv', 'env']:
                continue
            
            node = {
                'name': item.name,
                'path': str(item),
                'is_file': item.is_file(),
                'is_dir': item.is_dir(),
                'icon': get_file_icon(item) if item.is_file() else '📁',
                'children': []
            }
            
            if item.is_dir():
                node['children'] = build_file_tree(item, max_depth, current_depth + 1)
            
            tree.append(node)
    except PermissionError:
        pass
    
    return tree


def flatten_file_tree(tree: List[Dict], base_path: Path, prefix: str = "") -> List[Dict]:
    """Flatten file tree into a list with hierarchical display names"""
    files = []
    
    for node in tree:
        if node['is_file']:
            rel_path = Path(node['path']).relative_to(base_path)
            display_name = f"{prefix}{node['icon']} {node['name']}"
            files.append({
                'display': display_name,
                'path': node['path'],
                'relative_path': str(rel_path),
                'icon': node['icon']
            })
        else:
            # Recursively add children with indentation
            files.extend(flatten_file_tree(node['children'], base_path, prefix + "  "))
    
    return files


def render_file_tree(tree: List[Dict], base_path: Path, selected_file: Optional[str] = None) -> Optional[str]:
    """Render file tree with hierarchical display, return selected file path"""
    # Flatten tree for easier selection
    flat_files = flatten_file_tree(tree, base_path)
    
    if not flat_files:
        st.info("No files found in project")
        return None
    
    # Create list of display names with paths
    file_options = [f["relative_path"] for f in flat_files]
    file_paths = {f["relative_path"]: f["path"] for f in flat_files}
    file_displays = {f["relative_path"]: f["display"] for f in flat_files}
    
    # Use selectbox for file selection
    current_selection = selected_file
    if current_selection:
        # Find the relative path for currently selected file
        try:
            current_selection_rel = str(Path(current_selection).relative_to(base_path))
            if current_selection_rel in file_options:
                current_selection = current_selection_rel
        except:
            pass
    
    selected_relative = st.selectbox(
        "📄 Select a file to preview:",
        options=[""] + file_options,
        format_func=lambda x: file_displays.get(x, x) if x else "👆 Choose a file to preview...",
        index=0 if not current_selection or current_selection not in file_options else (
            file_options.index(current_selection) + 1
        ),
        key="file_selector"
    )
    
    if selected_relative and selected_relative in file_paths:
        return file_paths[selected_relative]
    
    return None


def render_tree_visual(tree: List[Dict], base_path: Path):
    """Render visual tree structure"""
    for node in tree:
        _render_tree_node(node, base_path, "")


def _render_tree_node(node: Dict, base_path: Path, indent: str):
    """Recursively render tree node for visual display"""
    if node['is_file']:
        rel_path = Path(node['path']).relative_to(base_path)
        st.markdown(f"{indent}{node['icon']} `{node['name']}`")
    else:
        with st.expander(f"{indent}{node['icon']} {node['name']}/", expanded=True):
            for child in node['children']:
                _render_tree_node(child, base_path, indent + "  ")


def get_code_language(file_path: Path) -> str:
    """Get language for syntax highlighting based on file extension"""
    suffix = file_path.suffix.lower()
    
    lang_map = {
        '.py': 'python',
        '.js': 'javascript',
        '.jsx': 'jsx',
        '.ts': 'typescript',
        '.tsx': 'tsx',
        '.html': 'html',
        '.css': 'css',
        '.json': 'json',
        '.md': 'markdown',
        '.yml': 'yaml',
        '.yaml': 'yaml',
        '.toml': 'toml',
        '.sh': 'bash',
        '.bat': 'batch',
        '.sql': 'sql',
        '.dockerfile': 'dockerfile',
        '.env': 'bash',
        '.gitignore': 'gitignore',
    }
    
    return lang_map.get(suffix, 'text')


def preview_file(file_path: Path, max_lines: int = 500) -> Optional[str]:
    """Read and return file content, truncated if too long"""
    try:
        # Try to read as text
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            lines = f.readlines()
            
            if len(lines) > max_lines:
                content = ''.join(lines[:max_lines])
                content += f"\n\n... ({len(lines) - max_lines} more lines truncated) ..."
            else:
                content = ''.join(lines)
            
            return content
    except Exception as e:
        return f"Error reading file: {str(e)}"

def can_render_preview(file_path: Path) -> bool:
    """Check if file can be rendered as live preview"""
    extension = file_path.suffix.lower()
    return extension in ['.html', '.htm', '.svg', '.md']

def render_file_preview(file_path: Path) -> tuple[str, str]:
    """Render file for live preview - returns (content, render_type)"""
    try:
        extension = file_path.suffix.lower()
        
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        if extension in ['.html', '.htm']:
            return content, 'html'
        elif extension == '.svg':
            return content, 'svg'
        elif extension == '.md':
            return content, 'markdown'
        else:
            return content, 'text'
            
    except Exception as e:
        return f"Error rendering file: {str(e)}", 'error'

