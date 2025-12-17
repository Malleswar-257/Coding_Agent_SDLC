"""
Content Parsers - Unified module for parsing JSON, files, and extracting content
Consolidates RobustJSONParser, FileParser, and ImpactAnalyzer into a single efficient module.
"""

import json
import re
from typing import Dict, Any, List, Optional
from pathlib import Path
import PyPDF2
from docx import Document
from utils.logger import StreamlitLogger
from utils.code_fixer import unescape_content


class RobustJSONParser:
    """Robust JSON parser with extensive error recovery mechanisms"""
    
    def __init__(self, logger=None, code_fixer=None):
        """
        Initialize the JSON parser.
        
        Args:
            logger: Optional logger instance for logging messages
            code_fixer: Optional CodeFixer instance for advanced JSON fixes
        """
        self.logger = logger
        self.code_fixer = code_fixer
    
    def log(self, message: str, level: str = "info"):
        """Log a message if logger is available"""
        if self.logger:
            if level == "error":
                self.logger.log(message, level="error")
            elif level == "warning":
                self.logger.log(message, level="warning")
            else:
                self.logger.log(message)
    
    def extract_json_from_content(self, content: str) -> str:
        """
        Extract JSON object from content (handles markdown code blocks, etc.)
        
        Args:
            content: Raw content that may contain JSON
            
        Returns:
            Extracted JSON string
        """
        # Method 1: Extract from markdown code blocks
        json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', content, re.DOTALL)
        if json_match:
            return json_match.group(1)
        
        # Method 2: Find JSON object directly using balanced braces
        start_idx = content.find('{')
        if start_idx != -1:
            brace_count = 0
            in_string = False
            escape_next = False
            
            for i in range(start_idx, len(content)):
                char = content[i]
                
                # Handle string literals (don't count braces inside strings)
                if escape_next:
                    escape_next = False
                    continue
                if char == '\\':
                    escape_next = True
                    continue
                if char == '"' and not escape_next:
                    in_string = not in_string
                    continue
                
                if not in_string:
                    if char == '{':
                        brace_count += 1
                    elif char == '}':
                        brace_count -= 1
                        if brace_count == 0:
                            return content[start_idx:i+1]
            
            if brace_count > 0:
                # JSON is incomplete, try to complete it
                self.log(f"⚠️ JSON appears incomplete (missing {brace_count} closing braces), attempting to fix...")
                return content[start_idx:] + '}' * brace_count
        
        # Fallback: try simple regex
        json_match = re.search(r'\{[\s\S]*\}', content)
        if json_match:
            return json_match.group(0)
        
        return content
    
    def parse(self, content: str, extract_first: bool = True) -> Dict[str, Any]:
        """
        Main entry point for parsing JSON with automatic fixes.
        
        Args:
            content: JSON string to parse (may be malformed)
            extract_first: If True, extract JSON from markdown/text first
            
        Returns:
            Parsed JSON as dictionary
            
        Raises:
            ValueError: If JSON cannot be parsed after all fix attempts
        """
        # First, extract JSON if needed
        if extract_first:
            content = self.extract_json_from_content(content)
        
        # Try to parse with fixes
        return self._parse_with_fixes(content)
    
    def _parse_with_fixes(self, content: str) -> Dict[str, Any]:
        """Parse JSON with automatic fixes for common errors"""
        # Try parsing first
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            error_msg = str(e)
            self.log(f"⚠️ JSON parse error: {error_msg}, attempting fixes...")
            
            # Fix 1: Handle unterminated strings
            if "Unterminated string" in error_msg or "Unterminated" in error_msg:
                self.log(f"⚠️ Attempting to fix unterminated string in JSON...")
                original_content = content
                content = self._fix_unterminated_strings(content)
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e2:
                    self.log(f"⚠️ Still invalid after string fix: {str(e2)}")
                    content = self._fix_unterminated_strings(original_content)
                    content = self._fix_missing_commas(content)
                    try:
                        return json.loads(content)
                    except json.JSONDecodeError:
                        pass
            
            # Fix 2: Handle missing commas
            if "Expecting ',' delimiter" in error_msg or "delimiter" in error_msg.lower():
                self.log(f"⚠️ Attempting to fix missing commas in JSON...")
                if "Unterminated" in error_msg:
                    content = self._fix_unterminated_strings(content)
                
                # Try using CodeFixer's JSON comma fixer first (if available)
                if self.code_fixer:
                    try:
                        fixed_content = self.code_fixer._fix_json_missing_commas(content, "JSON")
                        result = json.loads(fixed_content)
                        self.log(f"✅ Successfully fixed JSON with CodeFixer comma fixer")
                        return result
                    except (json.JSONDecodeError, AttributeError):
                        pass
                
                # Try fixing commas multiple times
                for comma_attempt in range(3):
                    try:
                        fixed_content = self._fix_missing_commas(content)
                        result = json.loads(fixed_content)
                        self.log(f"✅ Successfully fixed JSON after {comma_attempt + 1} comma fix attempts")
                        return result
                    except (json.JSONDecodeError, Exception) as e2:
                        if comma_attempt < 2:
                            content = fixed_content
                            continue
                        self.log(f"⚠️ Still invalid after comma fix: {str(e2)}")
            
            # Fix 3: Handle missing closing braces/brackets
            open_braces = content.count('{') - content.count('}')
            open_brackets = content.count('[') - content.count(']')
            if open_braces > 0 or open_brackets > 0:
                self.log(f"⚠️ Adding {open_braces} closing braces and {open_brackets} closing brackets...")
                if open_braces > 0:
                    content += '}' * open_braces
                if open_brackets > 0:
                    content += ']' * open_brackets
                try:
                    return json.loads(content)
                except json.JSONDecodeError as e2:
                    self.log(f"⚠️ Still invalid after brace fix: {str(e2)}")
            
            # Fix 4: Try using CodeFixer's JSON fixer (if available)
            if self.code_fixer:
                self.log(f"⚠️ Trying CodeFixer JSON fixes...")
                try:
                    fixed_content = self.code_fixer.fix_json(content, "JSON", error_msg)
                    result = json.loads(fixed_content)
                    self.log(f"✅ Successfully fixed JSON with CodeFixer")
                    return result
                except (json.JSONDecodeError, AttributeError) as e3:
                    self.log(f"⚠️ CodeFixer JSON fix failed: {str(e3)}")
            
            # Fix 5: Try position-based comma fixing
            if "Expecting ',' delimiter" in error_msg:
                self.log(f"⚠️ Attempting position-based comma fix...")
                fixed_content = content
                
                if hasattr(e, 'pos') and e.pos:
                    try:
                        fixed_content = self._fix_commas_at_position(fixed_content, e.pos)
                        result = json.loads(fixed_content)
                        self.log(f"✅ Successfully fixed JSON with position-based fix at {e.pos}")
                        return result
                    except (json.JSONDecodeError, AttributeError):
                        pass
                
                # Parse line/column from error message
                line_match = re.search(r'line (\d+)', error_msg)
                col_match = re.search(r'column (\d+)', error_msg)
                if line_match and col_match:
                    try:
                        line_num = int(line_match.group(1))
                        col_num = int(col_match.group(1))
                        lines = fixed_content.split('\n')
                        if line_num <= len(lines):
                            pos = sum(len(lines[i]) + 1 for i in range(line_num - 1)) + col_num - 1
                            fixed_content = self._fix_commas_at_position(fixed_content, pos)
                            result = json.loads(fixed_content)
                            self.log(f"✅ Successfully fixed JSON with line/column-based fix (line {line_num}, col {col_num})")
                            return result
                    except (json.JSONDecodeError, ValueError, IndexError):
                        pass
                
                # Aggressive comma insertion
                try:
                    fixed_content = self._fix_commas_aggressive(fixed_content, error_msg)
                    result = json.loads(fixed_content)
                    self.log(f"✅ Successfully fixed JSON with aggressive comma fix")
                    return result
                except json.JSONDecodeError:
                    pass
            
            # Fix 6: Try combining fixes
            self.log(f"⚠️ Trying combined fixes...")
            for attempt in range(3):
                combined_content = content
                combined_content = self._fix_unterminated_strings(combined_content)
                
                for _ in range(3):
                    combined_content = self._fix_missing_commas(combined_content)
                    if self.code_fixer:
                        try:
                            combined_content = self.code_fixer._fix_json_missing_commas(combined_content, "JSON")
                        except AttributeError:
                            pass
                    if "Expecting ',' delimiter" in error_msg:
                        combined_content = self._fix_commas_aggressive(combined_content, error_msg)
                
                if self.code_fixer and ("property name" in error_msg.lower() or "enclosed in double quotes" in error_msg.lower()):
                    try:
                        combined_content = self.code_fixer._fix_json_property_names(combined_content, "JSON")
                    except AttributeError:
                        pass
                
                open_braces = combined_content.count('{') - combined_content.count('}')
                open_brackets = combined_content.count('[') - combined_content.count(']')
                if open_braces > 0:
                    combined_content += '}' * open_braces
                if open_brackets > 0:
                    combined_content += ']' * open_brackets
                
                try:
                    result = json.loads(combined_content)
                    self.log(f"✅ Successfully fixed JSON with combined fixes")
                    return result
                except json.JSONDecodeError as e3:
                    if attempt < 2:
                        continue
                    self.log(f"⚠️ Combined fixes failed: {str(e3)}")
            
            # Final attempt: Extract partial JSON
            self.log(f"⚠️ JSON still invalid after all fix attempts, extracting partial JSON...")
            try:
                partial_result = self._parse_partial_json(content)
                if partial_result:
                    self.log(f"✅ Successfully extracted {len(partial_result)} files from partial JSON")
                    return partial_result
            except Exception as e_partial:
                self.log(f"⚠️ Partial JSON extraction failed: {str(e_partial)}")
            
            # If all else fails, raise error
            raise ValueError(f"Could not parse JSON after all fix attempts: {error_msg}")
    
    def _fix_unterminated_strings(self, json_str: str) -> str:
        """Fix unterminated strings in JSON by closing them properly"""
        result = []
        in_string = False
        escape_next = False
        i = 0
        
        while i < len(json_str):
            char = json_str[i]
            
            if escape_next:
                result.append(char)
                escape_next = False
                i += 1
                continue
            
            if char == '\\':
                escape_next = True
                result.append(char)
                i += 1
                continue
            
            if char == '"':
                if in_string:
                    lookahead_start = i + 1
                    while lookahead_start < len(json_str) and json_str[lookahead_start] in ' \t\n\r':
                        lookahead_start += 1
                    
                    if lookahead_start >= len(json_str):
                        in_string = False
                        result.append(char)
                    elif json_str[lookahead_start] in [':', ',', '}', ']', '\n']:
                        in_string = False
                        result.append(char)
                    else:
                        result.append(char)
                else:
                    in_string = True
                    result.append(char)
            else:
                result.append(char)
            
            i += 1
        
        # If we're still in a string at the end, close it
        if in_string:
            result.append('"')
        
        return ''.join(result)
    
    def _fix_missing_commas(self, json_str: str) -> str:
        """Fix missing commas in JSON using both regex and character-by-character parsing"""
        try:
            fixed = json_str
            
            # Comprehensive comma fixing with regex
            fixed = re.sub(r'([}\]])"(\s*)"([^:]+)":', r'\1,\2"\3":', fixed)
            fixed = re.sub(r'([}\]])"(\s*)"([{[])', r'\1,\2\3', fixed)
            fixed = re.sub(r'("(?:[^"\\]|\\.)*")\s*"([^:]+)":', r'\1, "\2":', fixed)
            fixed = re.sub(r'([0-9]+|true|false|null)\s*"([^:]+)":', r'\1, "\2":', fixed)
            fixed = re.sub(r'([}\]])"([^:]+)":', r'\1, "\2":', fixed)
            fixed = re.sub(r'("(?:[^"\\]|\\.)*")\s*([}\]])', r'\1, \2', fixed)
            fixed = re.sub(r'([0-9]+|true|false|null)\s*([}\]])', r'\1, \2', fixed)
            fixed = re.sub(r'([}\]])"(\s*)([0-9]+|true|false|null)', r'\1, \2\3', fixed)
            fixed = re.sub(r'([}\]])"(\s*)([{[])', r'\1, \2\3', fixed)
            
            # Character-by-character parsing for edge cases
            fixed = self._fix_missing_commas_char_by_char(fixed)
            
            return fixed
        except re.error as e:
            self.log(f"⚠️ Regex error in _fix_missing_commas: {str(e)}, trying character-by-character approach", level="warning")
            return self._fix_missing_commas_char_by_char(json_str)
    
    def _fix_missing_commas_char_by_char(self, json_str: str) -> str:
        """Fix missing commas by parsing character by character"""
        result = []
        i = 0
        in_string = False
        escape_next = False
        last_char = None
        
        while i < len(json_str):
            char = json_str[i]
            
            if escape_next:
                escape_next = False
                result.append(char)
                last_char = char
                i += 1
                continue
            
            if char == '\\':
                escape_next = True
                result.append(char)
                last_char = char
                i += 1
                continue
            
            if char == '"':
                if not in_string:
                    in_string = True
                else:
                    in_string = False
                result.append(char)
                last_char = char
                i += 1
                continue
            
            if not in_string:
                if last_char in ['}', ']'] and char == '"':
                    lookahead = json_str[i:].lstrip()
                    if ':' in lookahead[:50]:
                        result.append(',')
                        self.log(f"🔧 Added missing comma after {last_char}")
                
                elif last_char in ['}', ']'] and char in ['{', '[']:
                    result.append(',')
                    self.log(f"🔧 Added missing comma after {last_char}")
                
                elif last_char == '"' and char == '"':
                    if len(result) > 1 and result[-2] in [':', ',']:
                        lookahead = json_str[i:].lstrip()
                        if ':' in lookahead[:50]:
                            result.append(',')
                            self.log(f"🔧 Added missing comma between values")
                
                elif last_char in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'e', 'l', 'u', 'r', 'a', 's', 'f', 't', 'n'] and char == '"':
                    lookahead = json_str[i:].lstrip()
                    if ':' in lookahead[:50]:
                        result.append(',')
                        self.log(f"🔧 Added missing comma after value")
            
            result.append(char)
            last_char = char
            i += 1
        
        return ''.join(result)
    
    def _fix_commas_at_position(self, json_str: str, error_pos: int) -> str:
        """Fix missing comma at a specific position in JSON"""
        if error_pos < 0 or error_pos >= len(json_str):
            return json_str
        
        result = list(json_str)
        start_pos = max(0, error_pos - 300)
        search_area = json_str[start_pos:min(len(json_str), error_pos + 100)]
        
        in_string = False
        escape_next = False
        for j in range(len(search_area)):
            char = search_area[j]
            if escape_next:
                escape_next = False
                continue
            if char == '\\':
                escape_next = True
                continue
            if char == '"':
                in_string = not in_string
        
        if not in_string:
            for j in range(error_pos - 1, max(0, error_pos - 150), -1):
                char = json_str[j]
                is_value_end = False
                if char == '"':
                    is_value_end = True
                elif char in ['}', ']']:
                    is_value_end = True
                elif char in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9']:
                    k = j + 1
                    while k < len(json_str) and json_str[k] in ' \t\n\r':
                        k += 1
                    if k >= len(json_str) or json_str[k] not in '0123456789.eE+-':
                        is_value_end = True
                elif char in ['e', 'l', 'u', 'r', 'a', 's', 'f', 't', 'n']:
                    word_start = j
                    while word_start > 0 and json_str[word_start - 1] in 'abcdefghijklmnopqrstuvwxyz':
                        word_start -= 1
                    word = json_str[word_start:j+1]
                    if word in ['true', 'false', 'null']:
                        is_value_end = True
                
                if is_value_end:
                    next_char_idx = j + 1
                    while next_char_idx < len(json_str) and json_str[next_char_idx] in ' \t\n\r':
                        next_char_idx += 1
                    
                    if next_char_idx < len(json_str):
                        next_char = json_str[next_char_idx]
                        if next_char in ['"', '{', '[']:
                            has_comma = False
                            for k in range(j + 1, next_char_idx):
                                if json_str[k] == ',':
                                    has_comma = True
                                    break
                            
                            if not has_comma:
                                result.insert(next_char_idx, ',')
                                self.log(f"🔧 Added missing comma at position {next_char_idx} in JSON")
                                return ''.join(result)
        
        return json_str
    
    def _fix_commas_aggressive(self, json_str: str, error_msg: str) -> str:
        """Aggressively fix missing commas by scanning the entire JSON"""
        result = []
        i = 0
        in_string = False
        escape_next = False
        last_value_end = -1
        
        while i < len(json_str):
            char = json_str[i]
            
            if escape_next:
                escape_next = False
                result.append(char)
                i += 1
                continue
            
            if char == '\\':
                escape_next = True
                result.append(char)
                i += 1
                continue
            
            if char == '"':
                if not in_string:
                    in_string = True
                else:
                    in_string = False
                    last_value_end = len(result)
                result.append(char)
                i += 1
                continue
            
            if not in_string:
                if len(result) > 0 and result[-1] in ['}', ']'] and char == '"':
                    lookahead = json_str[i:].lstrip()
                    if lookahead.startswith('"') and ':' in lookahead[:100]:
                        result.append(',')
                        self.log(f"🔧 Added missing comma after {result[-1]} in JSON (aggressive)")
                
                elif len(result) > 0 and result[-1] in ['}', ']'] and char in ['{', '[']:
                    result.append(',')
                    self.log(f"🔧 Added missing comma after {result[-1]} in JSON (aggressive)")
                
                elif len(result) > 0 and result[-1] == '"' and char == '"' and last_value_end >= 0:
                    lookahead = json_str[i:].lstrip()
                    if ':' in lookahead[:100]:
                        result.append(',')
                        self.log(f"🔧 Added missing comma between values in JSON (aggressive)")
                
                elif len(result) > 0 and result[-1] in ['0', '1', '2', '3', '4', '5', '6', '7', '8', '9', 'e', 'l', 'u', 'r', 'a', 's', 'f', 't', 'n', '.'] and char == '"':
                    lookahead = json_str[i:].lstrip()
                    if ':' in lookahead[:100]:
                        result.append(',')
                        self.log(f"🔧 Added missing comma after value in JSON (aggressive)")
                
                if char in ['}', ']', '"']:
                    last_value_end = len(result)
            
            result.append(char)
            i += 1
        
        return ''.join(result)
    
    def _parse_partial_json(self, content: str) -> Dict[str, str]:
        """Try to parse partial/invalid JSON by extracting what we can"""
        result = {}
        
        pattern = r'"([^"]+)":\s*"((?:[^"\\]|\\.)*)"'
        matches = re.finditer(pattern, content, re.DOTALL)
        
        for match in matches:
            key = match.group(1)
            value = match.group(2)
            value = unescape_content(value).replace('\\"', '"').replace('\\\\', '\\')
            result[key] = value
        
        if result:
            self.log(f"⚠️ Extracted {len(result)} files from partial JSON")
            return result
        
        self.log("⚠️ Could not extract any valid files from JSON, will retry...")
        raise ValueError("Could not parse JSON")


class FileParser:
    """Parser for extracting project configuration from various file formats"""
    
    def __init__(self, llm):
        self.llm = llm
    
    def parse_file(self, file_content: bytes, file_name: str, file_type: str) -> Dict[str, Any]:
        """Parse uploaded file and extract project details"""
        
        try:
            if file_type == "application/json":
                return self._parse_json(file_content)
            elif file_type == "application/pdf":
                return self._parse_pdf(file_content)
            elif file_type == "application/vnd.openxmlformats-officedocument.wordprocessingml.document":
                return self._parse_docx(file_content)
            elif file_type == "text/plain":
                return self._parse_text(file_content.decode('utf-8'))
            else:
                return {"error": f"Unsupported file type: {file_type}"}
        except Exception as e:
            return {"error": f"Error parsing file: {str(e)}"}
    
    def _parse_json(self, file_content: bytes) -> Dict[str, Any]:
        """Parse JSON file for project configuration"""
        try:
            data = json.loads(file_content.decode('utf-8'))
            
            if all(key in data for key in ["project_name", "description", "frontend_stack", "backend_stack"]):
                return {
                    "project_name": data.get("project_name", ""),
                    "description": data.get("description", ""),
                    "frontend_stack": data.get("frontend_stack", "React + Vite"),
                    "backend_stack": data.get("backend_stack", "FastAPI + SQLAlchemy")
                }
            
            return self._extract_with_llm(json.dumps(data, indent=2))
            
        except json.JSONDecodeError:
            return {"error": "Invalid JSON format"}
    
    def _parse_pdf(self, file_content: bytes) -> Dict[str, Any]:
        """Parse PDF file for project configuration"""
        try:
            from io import BytesIO
            pdf_reader = PyPDF2.PdfReader(BytesIO(file_content))
            
            text = ""
            for page in pdf_reader.pages:
                text += page.extract_text() + "\n"
            
            return self._extract_with_llm(text)
            
        except Exception as e:
            return {"error": f"Error reading PDF: {str(e)}"}
    
    def _parse_docx(self, file_content: bytes) -> Dict[str, Any]:
        """Parse DOCX file for project configuration"""
        try:
            from io import BytesIO
            doc = Document(BytesIO(file_content))
            
            text = ""
            for paragraph in doc.paragraphs:
                text += paragraph.text + "\n"
            
            return self._extract_with_llm(text)
            
        except Exception as e:
            return {"error": f"Error reading DOCX: {str(e)}"}
    
    def _parse_text(self, text: str) -> Dict[str, Any]:
        """Parse plain text file for project configuration"""
        return self._extract_with_llm(text)
    
    def _extract_with_llm(self, content: str) -> Dict[str, Any]:
        """Use LLM to extract project details from any text content"""
        
        prompt = f"""
        Extract project configuration from the following content. Return a JSON object with these exact fields:
        - project_name: A suitable project name (kebab-case, no spaces)
        - frontend_stack: One of ["React + Vite", "Next.js 14", "Vue 3 + Vite", "SvelteKit"] (extract if mentioned, otherwise use "React + Vite")
        - backend_stack: One of ["FastAPI + SQLAlchemy", "Django", "Node.js/Express + Prisma", "Supabase", "Firebase"] (extract if mentioned, otherwise use "FastAPI + SQLAlchemy")
        - description: ALL remaining content after extracting the above fields. This should be the full project description, requirements, features, and any other details. Include everything that is not project_name, frontend_stack, or backend_stack.
        
        IMPORTANT: The description field should contain ALL the remaining content from the original text after extracting project_name, frontend_stack, and backend_stack. Do not summarize - include the full remaining content.
        
        Content to analyze:
        {content}
        
        Return only valid JSON, no other text:
        """
        
        try:
            response = self.llm.invoke(prompt)
            result_text = response.content.strip()
            
            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].strip()
            
            parsed = json.loads(result_text)
            
            required_fields = ["project_name", "description", "frontend_stack", "backend_stack"]
            for field in required_fields:
                if field not in parsed:
                    parsed[field] = ""
            
            if not parsed.get("description") or len(parsed.get("description", "")) < 50:
                parsed["description"] = self._extract_remaining_as_description(content, parsed)
            
            return parsed
            
        except Exception as e:
            return self._extract_with_regex(content)
    
    def _extract_remaining_as_description(self, original_content: str, extracted: Dict[str, Any]) -> str:
        """Extract remaining content as description after removing extracted fields"""
        content = original_content
        
        if extracted.get("project_name"):
            project_name_variations = [
                extracted["project_name"],
                extracted["project_name"].replace("-", " "),
                extracted["project_name"].replace("-", "_"),
            ]
            for variant in project_name_variations:
                content = re.sub(re.escape(variant), "", content, flags=re.IGNORECASE)
        
        if extracted.get("frontend_stack"):
            content = re.sub(re.escape(extracted["frontend_stack"]), "", content, flags=re.IGNORECASE)
        
        if extracted.get("backend_stack"):
            content = re.sub(re.escape(extracted["backend_stack"]), "", content, flags=re.IGNORECASE)
        
        content = re.sub(r'\s+', ' ', content).strip()
        
        if not content or len(content) < 10:
            return original_content.strip()
        
        return content
    
    def _extract_with_regex(self, content: str) -> Dict[str, Any]:
        """Fallback regex extraction"""
        
        original_content = content
        
        frontend_patterns = {
            r'(?i)(?:react\s*\+\s*vite|react.*vite)': "React + Vite",
            r'(?i)(?:next\.?js\s*14|nextjs\s*14)': "Next.js 14",
            r'(?i)(?:vue\s*3\s*\+\s*vite|vue.*vite)': "Vue 3 + Vite",
            r'(?i)sveltekit': "SvelteKit"
        }
        
        backend_patterns = {
            r'(?i)(?:fastapi\s*\+\s*sqlalchemy|fastapi.*sqlalchemy)': "FastAPI + SQLAlchemy",
            r'(?i)django': "Django",
            r'(?i)(?:node\.?js.*express.*prisma|express.*prisma)': "Node.js/Express + Prisma",
            r'(?i)supabase': "Supabase",
            r'(?i)firebase': "Firebase"
        }
        
        result = {
            "project_name": "",
            "description": "",
            "frontend_stack": "React + Vite",
            "backend_stack": "FastAPI + SQLAlchemy"
        }
        
        for pattern, stack in frontend_patterns.items():
            if re.search(pattern, content):
                result["frontend_stack"] = stack
                content = re.sub(pattern, "", content, flags=re.IGNORECASE)
                break
        
        for pattern, stack in backend_patterns.items():
            if re.search(pattern, content):
                result["backend_stack"] = stack
                content = re.sub(pattern, "", content, flags=re.IGNORECASE)
                break
        
        lines = content.split('\n')
        for line in lines[:10]:
            line = line.strip()
            if len(line) > 5 and len(line) < 50 and not line.startswith('#'):
                project_name = re.sub(r'[^a-zA-Z0-9\s-]', '', line).strip().lower().replace(' ', '-')
                if project_name:
                    result["project_name"] = project_name
                    content = re.sub(re.escape(line), "", content, flags=re.IGNORECASE)
                    break
        
        content = re.sub(r'\s+', ' ', content).strip()
        if content and len(content) > 10:
            result["description"] = content[:200000]
        else:
            result["description"] = original_content[:200000]
        
        return result


class ImpactAnalyzer:
    """Extracts API endpoints and their input fields from impact analysis reports"""
    
    def __init__(self, logger: Optional[StreamlitLogger] = None):
        self.logger = logger or StreamlitLogger()
    
    def log(self, message: str, level: str = "info"):
        """Log a message if logger is available"""
        if self.logger:
            if level == "error":
                self.logger.log(message, level="error")
            elif level == "warning":
                self.logger.log(message, level="warning")
            else:
                self.logger.log(message)
    
    def extract_endpoints_from_text(self, content: str) -> List[Dict[str, Any]]:
        """
        Extract API endpoints from impact analysis text content.
        
        Args:
            content: Text content from impact analysis report
            
        Returns:
            List of endpoint dictionaries with method, path, description, request_body, etc.
        """
        endpoints = []
        
        # Try to parse as JSON first
        try:
            data = json.loads(content)
            if isinstance(data, dict) and "endpoints" in data:
                endpoints = data["endpoints"]
            elif isinstance(data, list):
                endpoints = data
            if endpoints:
                self.log(f"✅ Extracted {len(endpoints)} endpoints from JSON format")
                return self._normalize_endpoints(endpoints)
        except (json.JSONDecodeError, KeyError):
            pass
        
        # Pattern 1: REST endpoints with methods
        method_pattern = r'\b(GET|POST|PUT|DELETE|PATCH|PUT|PATCH)\s+([/\w\-{}]+)'
        matches = re.finditer(method_pattern, content, re.IGNORECASE | re.MULTILINE)
        
        for match in matches:
            method = match.group(1).upper()
            path = match.group(2).strip()
            
            start_pos = max(0, match.start() - 200)
            end_pos = min(len(content), match.end() + 500)
            context = content[start_pos:end_pos]
            
            description = self._extract_description(context, match.group(0))
            request_body = self._extract_request_fields(context, path)
            response_fields = self._extract_response_fields(context)
            
            endpoint = {
                "method": method,
                "path": path,
                "description": description or f"{method} {path}",
                "request_body": request_body,
                "response": response_fields or {}
            }
            
            if not any(e["method"] == endpoint["method"] and e["path"] == endpoint["path"] 
                      for e in endpoints):
                endpoints.append(endpoint)
        
        # Pattern 2: Markdown format
        md_pattern = r'###\s*(GET|POST|PUT|DELETE|PATCH)\s+([/\w\-{}]+)\s*[-–]\s*(.+?)(?=\n###|\n##|\Z)'
        md_matches = re.finditer(md_pattern, content, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        for match in md_matches:
            method = match.group(1).upper()
            path = match.group(2).strip()
            description = match.group(3).strip()
            
            section_content = match.group(0)
            request_body = self._extract_request_fields(section_content, path)
            response_fields = self._extract_response_fields(section_content)
            
            endpoint = {
                "method": method,
                "path": path,
                "description": description,
                "request_body": request_body,
                "response": response_fields or {}
            }
            
            if not any(e["method"] == endpoint["method"] and e["path"] == endpoint["path"] 
                      for e in endpoints):
                endpoints.append(endpoint)
        
        # Pattern 3: Structured lists
        list_pattern = r'[-*•]\s*(GET|POST|PUT|DELETE|PATCH)\s+([/\w\-{}]+)\s*[\(:]?\s*(.+?)(?=\n[-*•]|\n\n|\Z)'
        list_matches = re.finditer(list_pattern, content, re.IGNORECASE | re.MULTILINE | re.DOTALL)
        
        for match in list_matches:
            method = match.group(1).upper()
            path = match.group(2).strip()
            fields_text = match.group(3).strip().rstrip(')')
            
            request_body = self._parse_fields_text(fields_text)
            
            endpoint = {
                "method": method,
                "path": path,
                "description": f"{method} {path}",
                "request_body": request_body,
                "response": {}
            }
            
            if not any(e["method"] == endpoint["method"] and e["path"] == endpoint["path"] 
                      for e in endpoints):
                endpoints.append(endpoint)
        
        normalized = self._normalize_endpoints(endpoints)
        if normalized:
            self.log(f"✅ Extracted {len(normalized)} endpoints from impact analysis")
        
        return normalized
    
    def _extract_description(self, context: str, endpoint_match: str) -> str:
        """Extract description text near the endpoint"""
        lines = context.split('\n')
        for i, line in enumerate(lines):
            if endpoint_match in line:
                parts = line.split(endpoint_match, 1)
                if len(parts) > 1 and parts[1].strip():
                    desc = parts[1].strip()
                    desc = re.sub(r'^[-–:]\s*', '', desc)
                    if len(desc) > 5:
                        return desc[:200]
                if i + 1 < len(lines):
                    next_line = lines[i + 1].strip()
                    if next_line and not next_line.startswith(('GET', 'POST', 'PUT', 'DELETE')):
                        return next_line[:200]
        return ""
    
    def _extract_request_fields(self, context: str, path: str) -> Dict[str, str]:
        """Extract request body fields from context"""
        fields = {}
        
        field_pattern = r'(\w+)\s*[:\-\(]\s*(\w+)(?:\)|,|\s|$)'
        field_matches = re.finditer(field_pattern, context, re.IGNORECASE)
        
        for match in field_matches:
            field_name = match.group(1).strip()
            field_type = match.group(2).strip()
            skip_words = ['request', 'response', 'body', 'method', 'path', 'endpoint', 'api', 'http', 'status', 'code', 'error', 'message']
            if field_name.lower() not in skip_words and len(field_name) > 1:
                type_mapping = {
                    'str': 'string', 'string': 'string',
                    'int': 'integer', 'integer': 'integer', 'number': 'integer',
                    'bool': 'boolean', 'boolean': 'boolean',
                    'float': 'float', 'double': 'float',
                    'date': 'date', 'datetime': 'datetime',
                    'list': 'array', 'array': 'array',
                    'dict': 'object', 'object': 'object'
                }
                normalized_type = type_mapping.get(field_type.lower(), field_type.lower())
                fields[field_name] = normalized_type
        
        json_pattern = r'\{[^}]*"(\w+)"\s*:\s*"?([^",}]+)"?'
        json_matches = re.finditer(json_pattern, context)
        
        for match in json_matches:
            field_name = match.group(1)
            field_value = match.group(2).strip().strip('"')
            field_type = "string"
            if field_value.isdigit():
                field_type = "integer"
            elif field_value.replace('.', '', 1).isdigit():
                field_type = "float"
            elif field_value.lower() in ['true', 'false']:
                field_type = "boolean"
            elif field_value.lower() in ['null', 'none']:
                field_type = "null"
            fields[field_name] = field_type
        
        table_pattern = r'(\w+)\s*\|\s*(\w+)'
        table_matches = re.finditer(table_pattern, context)
        
        for match in table_matches:
            field_name = match.group(1).strip()
            field_type = match.group(2).strip()
            if field_name.lower() not in ['field', 'name', 'parameter', 'input']:
                type_mapping = {
                    'str': 'string', 'string': 'string',
                    'int': 'integer', 'integer': 'integer',
                    'bool': 'boolean', 'boolean': 'boolean'
                }
                normalized_type = type_mapping.get(field_type.lower(), field_type.lower())
                fields[field_name] = normalized_type
        
        input_section_pattern = r'(?:input|parameters|fields|request\s+body)[:\-]?\s*(.+?)(?=\n\n|\nresponse|\n###|\Z)'
        input_match = re.search(input_section_pattern, context, re.IGNORECASE | re.DOTALL)
        if input_match:
            input_text = input_match.group(1)
            parsed = self._parse_fields_text(input_text)
            fields.update(parsed)
        
        return fields
    
    def _extract_response_fields(self, context: str) -> Dict[str, str]:
        """Extract response fields from context"""
        if "response" in context.lower():
            response_match = re.search(r'response[:\-]?\s*(.+?)(?=\n\n|\nrequest|$)', 
                                      context, re.IGNORECASE | re.DOTALL)
            if response_match:
                response_section = response_match.group(1)
                return self._extract_request_fields(response_section, "")
        return {}
    
    def _parse_fields_text(self, fields_text: str) -> Dict[str, str]:
        """Parse field text like 'email: string, password: string' into dict"""
        fields = {}
        field_parts = re.split(r',\s*(?![^()]*\))', fields_text)
        for part in field_parts:
            part = part.strip()
            if not part:
                continue
            match = re.match(r'(\w+)\s*[:\-\(]\s*(\w+)', part)
            if match:
                field_name = match.group(1).strip()
                field_type = match.group(2).strip()
                type_mapping = {
                    'str': 'string', 'string': 'string',
                    'int': 'integer', 'integer': 'integer', 'number': 'integer',
                    'bool': 'boolean', 'boolean': 'boolean',
                    'float': 'float', 'double': 'float'
                }
                normalized_type = type_mapping.get(field_type.lower(), field_type.lower())
                fields[field_name] = normalized_type
        return fields
    
    def _normalize_endpoints(self, endpoints: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Normalize endpoint structure to ensure consistent format"""
        normalized = []
        for endpoint in endpoints:
            normalized_endpoint = {
                "method": endpoint.get("method", "GET").upper(),
                "path": endpoint.get("path", ""),
                "description": endpoint.get("description", endpoint.get("desc", "")),
                "request_body": endpoint.get("request_body", endpoint.get("requestBody", endpoint.get("inputs", {}))),
                "response": endpoint.get("response", endpoint.get("responseBody", {}))
            }
            
            if not isinstance(normalized_endpoint["request_body"], dict):
                normalized_endpoint["request_body"] = {}
            if not isinstance(normalized_endpoint["response"], dict):
                normalized_endpoint["response"] = {}
            
            normalized.append(normalized_endpoint)
        
        return normalized

