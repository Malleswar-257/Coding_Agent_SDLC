"""
CODE AGENT - Main Streamlit Application
Turns natural language prompts + tech stack choices into complete backend-focused projects
"""

import streamlit as st
import sys
from pathlib import Path
from typing import Optional, Dict, Any
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent))

from workflow.orchestrator import ProjectOrchestrator
from utils.logger import StreamlitLogger
from utils.file_browser import build_file_tree, render_file_tree, preview_file, get_code_language, render_tree_visual, can_render_preview, render_file_preview
from utils.content_parsers import FileParser
from utils.llm_manager import LLMFactory
# Removed ProjectRunner and ProjectPreview imports (no longer used)

# Page config
st.set_page_config(
    page_title="CODE AGENT",
    page_icon="🚀",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# Custom CSS for better UI
st.markdown("""
    <style>
    .main-header {
        font-size: 3rem;
        font-weight: bold;
        text-align: center;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        -webkit-background-clip: text;
        -webkit-text-fill-color: transparent;
        margin-bottom: 1rem;
    }
    .sub-header {
        text-align: center;
        color: #666;
        margin-bottom: 2rem;
    }
    .stButton>button {
        width: 100%;
        background: linear-gradient(90deg, #667eea 0%, #764ba2 100%);
        color: white;
        font-size: 1.2rem;
        font-weight: bold;
        padding: 0.75rem 2rem;
        border-radius: 0.5rem;
        border: none;
    }
    .stButton>button:hover {
        transform: translateY(-2px);
        box-shadow: 0 4px 12px rgba(102, 126, 234, 0.4);
    }
    </style>
""", unsafe_allow_html=True)

def _read_uploaded_file(uploaded) -> str:
    if uploaded is None:
        return ""
    file_bytes = uploaded.read()
    name_lower = uploaded.name.lower()
    mime = uploaded.type or ""
    if mime == "application/json" or name_lower.endswith(".json"):
        try:
            return file_bytes.decode("utf-8")
        except Exception:
            return ""
    if mime in ["text/plain", "text/markdown"] or name_lower.endswith((".txt", ".md")):
        try:
            return file_bytes.decode("utf-8")
        except Exception:
            return ""
    if mime == "application/pdf" or name_lower.endswith(".pdf"):
        try:
            import io
            import PyPDF2
            pdf_reader = PyPDF2.PdfReader(io.BytesIO(file_bytes))
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            return text
        except Exception:
            return ""
    return ""

def _project_name_from_repo(url: str) -> str:
    if not url:
        return ""
    trimmed = url.rstrip("/").split("/")[-1]
    return trimmed or ""

def main():
    st.markdown('<h1 class="main-header">🚀 CODE AGENT</h1>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">Transform your ideas into production-ready backend projects with <strong>OpenRouter.ai</strong></p>', unsafe_allow_html=True)
    
    # Initialize session state
    if 'generation_in_progress' not in st.session_state:
        st.session_state.generation_in_progress = False
    if 'logs' not in st.session_state:
        st.session_state.logs = []
    if 'zip_file' not in st.session_state:
        st.session_state.zip_file = None
    if 'project_directory' not in st.session_state:
        st.session_state.project_directory = None
    if 'selected_file' not in st.session_state:
        st.session_state.selected_file = None
    if 'file_tree' not in st.session_state:
        st.session_state.file_tree = None
    if 'project_name' not in st.session_state:
        st.session_state.project_name = None
    if 'github_url' not in st.session_state:
        st.session_state.github_url = None
    if 'github_result' not in st.session_state:
        st.session_state.github_result = None
    # Removed preview and run project session state variables
    if 'last_project_config' not in st.session_state:
        st.session_state.last_project_config = None
    # Removed preview-related session state variables
    
    # Initialize form values
    form_values = {
        "project_name": "",
        "backend_stack": "FastAPI + SQLAlchemy",
        "frontend_repo_url": "",
        "prd_content": ""
    }
    
    st.markdown("### ✏️ Manual Entry")
    st.markdown("Fill in the details manually or edit the extracted information:")

    # Main form
    with st.form("project_generator_form"):
        col1, col2 = st.columns(2)
        
        with col1:
            frontend_repo_url = st.text_input(
                "GitHub Frontend URL *",
                value=form_values.get("frontend_repo_url", ""),
                placeholder="https://github.com/username/frontend-repo",
                help="Repository containing the frontend code to integrate"
            )
            
            github_token = st.text_input(
                "GitHub Token (Optional)",
                value=form_values.get("github_token", ""),
                placeholder="ghp_... (only for private repos)",
                type="password"
            )

        with col2:
            backend_options = ["FastAPI + SQLAlchemy", "Django"]
            backend_index = 0
            if form_values["backend_stack"] in backend_options:
                backend_index = backend_options.index(form_values["backend_stack"])
            
            backend_stack = st.selectbox(
                "Backend Stack *",
                options=backend_options,
                index=backend_index,
                help="Choose your backend framework"
            )

        col_a, col_b = st.columns(2)
        with col_a:
            impact_file = st.file_uploader(
                "Impact Analysis Report (PDF/JSON/TXT) *",
                type=['pdf', 'json', 'txt'],
                help="Required: Contains API endpoints with input fields"
            )
        with col_b:
            prd_file = st.file_uploader(
                "PRD Document (PDF/JSON/TXT, optional)",
                type=['pdf', 'json', 'txt']
            )

        # Project name (auto from repo URL if left blank)
        project_name_input = _project_name_from_repo(frontend_repo_url) or form_values["project_name"]
        project_name = st.text_input(
            "Project Name (Auto-filled from URL)",
            value=project_name_input,
            placeholder="my-fullstack-app",
            help="Defaults to the repo name; you can override if needed"
        )

        # GitHub publishing option
        publish_to_github = st.checkbox("🐙 Publish to GitHub", help="Automatically create a GitHub repository and push your project")
        
        # API key option - use custom or default (hidden UI)
        use_custom_key = False
        api_key = None  # Always use default unless later overridden programmatically

        submitted = st.form_submit_button(
            "🚀 Generate Full Project",
            use_container_width=True
        )
    
    # Handle form submission
    if submitted and not st.session_state.generation_in_progress:
        # Validation - Impact Analysis is now required
        if not all([project_name, backend_stack, frontend_repo_url]):
            st.error("Please fill in all required fields (marked with *)")
            st.stop()
        
        # Validate that Impact Analysis report is uploaded
        if not impact_file:
            st.error("⚠️ Impact Analysis Report is required! Please upload a PDF, JSON, or TXT file containing API endpoints with input fields.")
            st.stop()
        
        # Validate API key if custom key is being used
        if use_custom_key and not api_key:
            st.error("⚠️ Please enter an OpenRouter API key or uncheck 'Use custom OpenRouter API key' to use the default")
            st.stop()
        
        st.session_state.generation_in_progress = True
        st.session_state.logs = []
        st.session_state.zip_file = None
        st.session_state.project_directory = None
        st.session_state.selected_file = None
        st.session_state.file_tree = None
        st.session_state.project_name = project_name
        st.session_state.last_project_config = None
        
        # Initialize logger
        logger = StreamlitLogger()
        
        # Read uploaded files (Impact Analysis is required)
        prd_content = _read_uploaded_file(prd_file) if prd_file else ""
        impact_content = _read_uploaded_file(impact_file) if impact_file else ""
        
        # Impact Analysis is required - if somehow missing, use empty string (validation should catch this)
        if not impact_content:
            impact_content = ""
        
        combined_prd = prd_content
        if impact_content:
            combined_prd = f"{combined_prd}\n\nImpact Analysis:\n{impact_content}".strip()
        elif prd_content:
            combined_prd = prd_content
        else:
            combined_prd = f"Backend generation request for repo {frontend_repo_url}"
        
        # Show progress area
        st.markdown("---")
        st.markdown("### 📊 Generation Progress")
        log_container = st.empty()
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        try:
            # Initialize orchestrator with API key (custom or default)
            selected_api_key = api_key if (use_custom_key and api_key) else None
            orchestrator = ProjectOrchestrator(
                api_key=selected_api_key,  # Use custom key if provided, otherwise None (uses default)
                logger=logger
            )
            
            # Prepare project config
            project_config = {
                "project_name": project_name,
                "description": combined_prd,
                "frontend_stack": "Provided GitHub frontend",
                "backend_stack": backend_stack,
                "frontend_repo_url": frontend_repo_url,
                "prd_content": prd_content,  # PRD only (not combined)
                "impact_analysis": impact_content,  # Impact analysis separately
                "publish_to_github": publish_to_github,
                "github_token": github_token
            }
            st.session_state.last_project_config = project_config
            
            # Run generation workflow
            with st.spinner("Initializing project generation..."):
                result = orchestrator.generate_project(project_config)
            
            # Update UI with logs
            update_logs_display(log_container, logger.get_logs())
            progress_bar.progress(1.0)
            status_text.success("✅ Project generated successfully!")
            
            # Get ZIP file path and project directory from result
            if result and result.get("project_path"):
                zip_path = result["project_path"]
                project_dir = result.get("project_directory")
                github_result = result.get("github_result")
                
                # Store project directory in session state
                if project_dir:
                    st.session_state.project_directory = project_dir
                
                # Store GitHub result and URL in session state
                if github_result:
                    st.session_state.github_result = github_result
                    if github_result.get("success"):
                        repo_url = github_result.get("repository_url")
                        if repo_url:
                            st.session_state.github_url = repo_url
                
                # Read ZIP file
                try:
                    with open(zip_path, "rb") as f:
                        zip_buffer = f.read()
                    st.session_state.zip_file = zip_buffer
                except Exception as e:
                    st.warning(f"ZIP file created at: {zip_path}")
                    st.error(f"Could not read ZIP file: {str(e)}")
            
        except Exception as e:
            error_message = str(e)
            logger.log(f"ERROR: {error_message}", level="error")
            update_logs_display(log_container, logger.get_logs())
            
            # Check for insufficient credits/payment required errors
            if "402" in error_message or "requires more credits" in error_message.lower() or "can only afford" in error_message.lower():
                st.error("💰 **Insufficient Credits Error**")
                st.warning(f"""
                **Your OpenRouter account doesn't have enough credits for this request.**
                
                **The Issue:**
                - You requested up to 16384 tokens, but can only afford 4000 tokens
                - This is a free tier limitation
                
                **Solutions:**
                1. ✅ **Upgrade Your OpenRouter Account** (Recommended)
                   - Visit: https://openrouter.ai/settings/credits
                   - Add credits to your account
                   - This allows you to use premium models like GPT-4o
                
                2. ✅ **Use a Free Model** (Quick Fix)
                   - The app will automatically use a free model (Llama 3.1 70B) for free tier
                   - This model is free but may be slower
                   - Try generating again - it should work now
                
                3. ✅ **Reduce Project Complexity**
                   - Try a smaller project description
                   - The app now limits to 4000 tokens to stay within free tier
                
                **Note:** The app has been updated to use free-tier compatible models and token limits.
                """)
            # Check for invalid API key errors
            elif "401" in error_message or "invalid_api_key" in error_message.lower() or "Invalid API Key" in error_message:
                st.error("🔑 **Invalid API Key Error**")
                st.warning(f"""
                **Your OpenRouter API key is invalid or expired.**
                
                **Quick Fix (Easiest):**
                1. ✅ **Get a new API key** from https://openrouter.ai/keys
                   - Sign up or log in
                   - Go to **API Keys** section
                   - Click **"Create Key"**
                   - Copy the key (starts with `sk-or-v1-`)
                
                2. ✅ **Use it in the app:**
                   - Check the **"Use custom OpenRouter API key"** checkbox above
                   - Paste your new key in the field
                   - Click **"🚀 Generate Full Project"** again
                
                **Alternative: Update .env file:**
                - Open `grok/.env` file
                - Replace the `OPENROUTER_API_KEY` value with your new key
                - Restart the Streamlit app
                
                **Note:** The default API key may have expired. Using your own key is recommended!
                """)
            # Check for rate limit errors
            elif "rate_limit" in error_message.lower() or "429" in error_message or "Rate limit" in error_message or "tokens per day" in error_message.lower():
                st.error("⚠️ **API Rate Limit Reached**")
                
                # Try to extract information from error message
                import re
                reset_match = re.search(r'Please try again in ([\d\.]+[smh])', error_message)
                limit_match = re.search(r'Limit (\d+)', error_message)
                
                st.warning(f"""
                **Your OpenRouter API key has reached its rate limit.**
                
                {f"⏰ **Reset time:** {reset_match.group(1)}" if reset_match else ""}
                {f"📊 **Daily limit:** {limit_match.group(1)} tokens" if limit_match else ""}
                
                **Solutions:**
                1. **⏳ Wait** - The limit will reset automatically
                2. **🔑 Use a different API key** - Get a key from https://openrouter.ai/keys
                   - Check "Use custom OpenRouter API key" in the form above
                   - Paste your new key
                3. **💎 Upgrade** - Upgrade your OpenRouter plan for higher limits at https://openrouter.ai/settings
                """)
            else:
                st.error(f"❌ Error during generation: {error_message}")
            
        finally:
            st.session_state.generation_in_progress = False
    
    # Display project files browser and preview
    if st.session_state.project_directory:
        project_dir_path = Path(st.session_state.project_directory)
        
        if project_dir_path.exists():
            st.markdown("---")
            st.markdown("## 📂 Project Files")
            
            # GitHub Results Display (if available)
            if hasattr(st.session_state, 'github_result') and st.session_state.github_result:
                github_result = st.session_state.github_result
                if github_result.get("success"):
                    st.success("🎉 Project published to GitHub successfully!")
                    repo_url = github_result.get("repository_url")
                    if repo_url:
                        st.markdown(f"🔗 **Repository URL:** [{repo_url}]({repo_url})")
                        st.markdown(f"📁 **Files uploaded:** {github_result.get('uploaded_files', 0)}")
                elif github_result.get("skip_reason") == "no_token":
                    st.info("💡 **GitHub publishing skipped** - No GitHub token configured")
                else:
                    error_msg = github_result.get('error', 'Unknown error')
                    # Check for authentication errors
                    if "401" in str(error_msg) or "Unauthorized" in str(error_msg) or "invalid" in str(error_msg).lower():
                        st.error("🔑 **GitHub Authentication Failed**")
                        st.warning(f"""
                        **Your GitHub token is invalid, expired, or missing required permissions.**
                        
                        **Quick Fix:**
                        1. ✅ **Get a new GitHub Personal Access Token:**
                           - Go to: https://github.com/settings/tokens
                           - Click **"Generate new token"** → **"Generate new token (classic)"**
                           - Give it a name (e.g., "CODE AGENT")
                           - Select scopes: ✅ **`repo`** (Full control of private repositories)
                           - Click **"Generate token"**
                           - **Copy the token immediately** (starts with `ghp_`)
                        
                        2. ✅ **Add it to your `.env` file:**
                           - Open `grok/.env` file
                           - Add or update: `GITHUB_ACCESS_TOKEN=ghp_your_token_here`
                           - Save the file
                        
                        3. ✅ **Restart the Streamlit app** for changes to take effect
                        
                        **Note:** The token needs `repo` scope to create and push to repositories.
                        """)
                    else:
                        st.warning(f"⚠️ GitHub publishing failed: {error_msg}")
            
            # Main action buttons
            col1, col2 = st.columns(2)
            
            with col1:
                if st.session_state.zip_file:
                    st.download_button(
                        label="📦 Download ZIP",
                        data=st.session_state.zip_file,
                        file_name=f"{st.session_state.project_name or 'project'}.zip",
                        mime="application/zip",
                        use_container_width=True
                    )
            
            with col2:
                # Show GitHub link if available
                if hasattr(st.session_state, 'github_url') and st.session_state.github_url:
                    st.link_button(
                        "🐙 View on GitHub",
                        st.session_state.github_url,
                        use_container_width=True
                    )

            # Removed Preview Project and Run Project buttons and their functionality
            
            # Build file tree if not already built
            if st.session_state.file_tree is None:
                st.session_state.file_tree = build_file_tree(project_dir_path)
            
            # Removed Project Preview Section
            
            # Removed Project Preview Section
            
            # Two column layout: file browser and preview
            col1, col2 = st.columns([1, 2])
            
            with col1:
                st.markdown("### 📁 File Explorer")
                
                # File selector dropdown
                clicked_file = render_file_tree(st.session_state.file_tree, project_dir_path, st.session_state.selected_file)
                
                if clicked_file:
                    st.session_state.selected_file = clicked_file
                
                # Show tree structure
                st.markdown("---")
                st.markdown("**📂 Project Structure:**")
                render_tree_visual(st.session_state.file_tree, project_dir_path)
            
            with col2:
                st.markdown("### 👁️ File Preview")
                
                if st.session_state.selected_file:
                    selected_path = Path(st.session_state.selected_file)
                    
                    if selected_path.exists() and selected_path.is_file():
                        file_name = selected_path.name
                        file_size = selected_path.stat().st_size
                        relative_path = selected_path.relative_to(project_dir_path)
                        
                        # File metadata
                        col_path, col_size = st.columns([3, 1])
                        with col_path:
                            st.markdown(f"**📄 File:** `{relative_path}`")
                        with col_size:
                            st.markdown(f"**Size:** {file_size:,} bytes")
                        
                        # Check if file can be rendered as preview
                        if can_render_preview(selected_path):
                            # Create tabs for code view and live preview
                            tab1, tab2 = st.tabs(["📝 Code", "🌐 Live Preview"])
                            
                            with tab1:
                                # Show code with syntax highlighting
                                content = preview_file(selected_path)
                                language = get_code_language(selected_path)
                                
                                if content:
                                    st.code(content, language=language, line_numbers=True)
                                else:
                                    st.warning("Could not preview this file type")
                            
                            with tab2:
                                # Show live preview
                                try:
                                    preview_content, render_type = render_file_preview(selected_path)
                                    
                                    if render_type == 'html':
                                        st.markdown("**🌐 HTML Preview:**")
                                        st.components.v1.html(preview_content, height=600, scrolling=True)
                                    elif render_type == 'svg':
                                        st.markdown("**🖼️ SVG Preview:**")
                                        st.image(preview_content)
                                    elif render_type == 'markdown':
                                        st.markdown("**📝 Markdown Preview:**")
                                        st.markdown(preview_content)
                                    else:
                                        st.warning("Live preview not available for this file type")
                                        
                                except Exception as e:
                                    st.error(f"Error rendering preview: {str(e)}")
                        else:
                            # Show only code view for non-previewable files
                            content = preview_file(selected_path)
                            language = get_code_language(selected_path)
                            
                            if content:
                                st.code(content, language=language, line_numbers=True)
                            else:
                                st.warning("Could not preview this file type")
                    else:
                        st.info("Please select a file from the explorer to preview")
                else:
                    st.info("👈 Click on a file in the explorer to preview it here")
    
    # Display logs if available
    if st.session_state.logs:
        with st.expander("📋 View Generation Logs", expanded=False):
            for log in st.session_state.logs[-50:]:  # Show last 50 logs
                st.text(log)

def update_logs_display(container, logs):
    """Update the log display container"""
    if logs:
        log_text = "\n".join([f"[{log.get('timestamp', '')}] {log.get('message', '')}" for log in logs[-30:]])
        container.text_area("Live Logs", log_text, height=400, disabled=True, key="live_logs")

# Removed create_zip_file - packager agent handles ZIP creation

if __name__ == "__main__":
    main()

