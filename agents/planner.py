"""
PlannerAgent - Converts user prompt into detailed spec, user stories, API endpoints
"""

from typing import Dict, Any
import json
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.messages import SystemMessage, HumanMessage
from utils.logger import StreamlitLogger
from utils.content_parsers import RobustJSONParser, ImpactAnalyzer

class PlannerAgent:
    """Agent that creates detailed project specifications"""
    
    def __init__(self, llm, logger: StreamlitLogger):
        self.llm = llm
        self.logger = logger
        self.json_parser = RobustJSONParser(logger=logger)
        self.impact_analyzer = ImpactAnalyzer(logger=logger)
    
    def create_spec(self, project_config: Dict[str, Any]) -> Dict[str, Any]:
        """Create detailed project specification from PRD and config"""
        self.logger.log("📋 Analyzing requirements and creating project specification...")
        prd_content = project_config.get("prd_content") or project_config.get("description", "")
        impact_content = project_config.get("impact_analysis", "") or project_config.get("impact_content", "")
        
        # Extract endpoints from impact analysis if available
        extracted_endpoints = []
        if impact_content:
            self.logger.log("📊 Extracting API endpoints from impact analysis report...")
            extracted_endpoints = self.impact_analyzer.extract_endpoints_from_text(impact_content)
            if extracted_endpoints:
                self.logger.log(f"✅ Found {len(extracted_endpoints)} endpoints in impact analysis")
        
        prompt = ChatPromptTemplate.from_messages([
            ("system", """You are an expert software architect. Your task is to analyze the provided PRD content (or description if PRD is missing) and create a comprehensive technical specification.

The PRD may already contain explicit API endpoints, API calls, and a backend stack. Treat PRD details as authoritative when present. If conflicts arise between PRD and other fields, prefer the PRD.

Create a detailed specification including:
1. Project overview and goals
2. User stories (as a user, I want...)
3. API endpoints (RESTful) with request/response schemas
4. Database schema (tables, relationships)
5. Authentication requirements
6. Key features and functionality
7. Technical requirements

CRITICAL JSON FORMATTING REQUIREMENTS:
- Return ONLY valid JSON - no markdown code blocks, no explanations
- Escape ALL quotes inside string values using \"
- Escape ALL newlines inside string values using \\n (NOT literal newlines)
- Escape ALL backslashes using \\
- Ensure ALL strings are properly closed with closing quotes
- Add commas between all JSON elements (arrays, objects, key-value pairs)
- Ensure ALL opening braces {{ and brackets [ have matching closing ones }}
- Test that your JSON is valid before returning it

Return your response as a structured JSON object with the following structure:
{{
    "overview": "Project overview",
    "user_stories": ["story1", "story2"],
    "api_endpoints": [
        {{
            "method": "GET",
            "path": "/api/endpoint",
            "description": "Endpoint description",
            "request_body": {{"field": "type"}},
            "response": {{"field": "type"}}
        }}
    ],
    "database_schema": {{
        "tables": [
            {{
                "name": "table_name",
                "fields": [
                    {{"name": "field_name", "type": "string", "required": true}}
                ],
                "relationships": []
            }}
        ]
    }},
    "authentication": {{
        "required": true,
        "method": "JWT",
        "features": ["login", "register"]
    }},
    "features": ["feature1", "feature2"],
    "technical_requirements": ["req1", "req2"],
    "backend_stack": "FastAPI + SQLAlchemy",
    "api_summary": {{
        "declared_endpoints": 5,
        "declared_external_api_calls": 0,
        "notes": "Any assumptions or gaps"
    }}
}}"""),
            ("human", """Project Name: {project_name}
Description: {description}
Frontend Stack: {frontend_stack}
Backend Stack: {backend_stack}
PRD Content (authoritative when present):
{prd_content}

Create a comprehensive technical specification for this project, ensuring API endpoints, API calls, and backend stack reflect the PRD when provided.""")
        ])
        
        # Prepare impact analysis section for prompt
        impact_analysis_section = ""
        if extracted_endpoints:
            endpoints_json = json.dumps(extracted_endpoints, indent=2)
            impact_analysis_section = f"""Impact Analysis - API Endpoints (USE THESE EXACT ENDPOINTS):
{endpoints_json}

CRITICAL: You MUST use these exact endpoints from the impact analysis. Copy them exactly as specified above. Do not generate new endpoints - use the ones provided in the impact analysis."""
        else:
            impact_analysis_section = ""
        
        try:
            messages = prompt.format_messages(
                project_name=project_config["project_name"],
                description=project_config["description"],
                frontend_stack=project_config["frontend_stack"],
                backend_stack=project_config["backend_stack"],
                prd_content=prd_content,
                impact_analysis_section=impact_analysis_section
            )
            
            response = self.llm.invoke(messages)
            content = response.content
            
            # Parse JSON from response using the robust JSON parser
            spec = self.json_parser.parse(content, extract_first=True)
            
            # Override API endpoints with extracted ones from impact analysis if available
            if extracted_endpoints:
                spec["api_endpoints"] = extracted_endpoints
                self.logger.log(f"✅ Using {len(extracted_endpoints)} endpoints from impact analysis (overriding generated ones)")
                
                # Display extracted endpoints with input fields
                self.logger.log("📋 Extracted API Endpoints from Impact Analysis:")
                for idx, endpoint in enumerate(extracted_endpoints, 1):
                    method = endpoint.get("method", "GET")
                    path = endpoint.get("path", "")
                    description = endpoint.get("description", "")
                    request_body = endpoint.get("request_body", {})
                    
                    self.logger.log(f"  {idx}. {method} {path}")
                    if description:
                        self.logger.log(f"     Description: {description}")
                    if request_body:
                        fields_str = ", ".join([f"{k}: {v}" for k, v in request_body.items()])
                        self.logger.log(f"     Input Fields: {fields_str}")
                    else:
                        self.logger.log(f"     Input Fields: (none)")
            
            self.logger.log(f"✅ Created specification with {len(spec.get('user_stories', []))} user stories and {len(spec.get('api_endpoints', []))} API endpoints")
            
            return spec
            
        except Exception as e:
            error_str = str(e)
            self.logger.log(f"⚠️ Error creating spec: {error_str}", level="error")
            
            # Check if this is an API error that should trigger fallback
            if "402" in error_str or "requires more credits" in error_str.lower() or "can only afford" in error_str.lower():
                self.logger.log("🔄 OpenRouter credits insufficient, falling back to Groq...")
            
            # Retry once with a simpler prompt (will use fallback if available)
            try:
                self.logger.log("🔄 Retrying with simplified prompt...")
                simple_prompt = f"""Create a JSON specification for this project (use PRD content when available, it is authoritative):

Project: {project_config['project_name']}
Description: {project_config['description']}
Frontend: {project_config['frontend_stack']}
Backend: {project_config['backend_stack']}
PRD:
{prd_content}

Return ONLY valid JSON with: overview, user_stories (array), api_endpoints (array), database_schema (object with tables array), authentication (object), features (array), technical_requirements (array), backend_stack, and api_summary (declared_endpoints count, declared_external_api_calls count, notes)."""
                
                retry_response = self.llm.invoke([("user", simple_prompt)])
                content = retry_response.content.strip()
                
                # Parse JSON using the robust JSON parser
                spec = self.json_parser.parse(content, extract_first=True)
                
                # Override API endpoints with extracted ones from impact analysis if available
                if extracted_endpoints:
                    spec["api_endpoints"] = extracted_endpoints
                    self.logger.log(f"✅ Using {len(extracted_endpoints)} endpoints from impact analysis in retry")
                
                self.logger.log(f"✅ Created specification with retry")
                return spec
            except Exception as retry_error:
                # Only use minimal fallback if retry also fails
                self.logger.log("❌ Both attempts failed", level="error")
                raise Exception(f"Failed to generate project specification: {error_str}")

