"""
CodeFixer - Comprehensive utility for fixing Python syntax and indentation errors
Handles all common syntax issues in generated code files
"""

import ast
import re
from typing import Optional


def unescape_content(content: str) -> str:
    """
    Unescape escape sequences in content (\\n -> newline, etc.)
    
    Args:
        content: String content that may contain escape sequences
        
    Returns:
        String with escape sequences converted to actual characters
        
    Examples:
        >>> unescape_content("Hello\\nWorld")
        'Hello\nWorld'
        >>> unescape_content("Tab\\tSeparated")
        'Tab\tSeparated'
    """
    return content.replace('\\n', '\n').replace('\\t', '\t').replace('\\r', '\r')


class CodeFixer:
    """Comprehensive code fixing utility for Python files"""
    
    def __init__(self, logger=None):
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
    
    def fix_all(self, code: str, file_path: str = "") -> str:
        """Apply all fixes to code"""
        if not file_path.endswith('.py'):
            return code
        
        # Apply fixes in order (order matters!)
        # 1. Fix strings first (they affect bracket counting)
        code = self.fix_unterminated_string_literals(code, file_path)
        # 2. Fix bracket mismatches
        code = self.fix_bracket_mismatches(code, file_path)
        # 3. Fix extra closing brackets
        code = self.fix_extra_closing_brackets(code, file_path)
        # 4. Fix missing colons
        code = self.fix_missing_colons(code, file_path)
        # 5. Fix indentation (should be last as it depends on structure)
        code = self.fix_missing_indentation(code, file_path)
        
        return code
    
    def validate_and_fix(self, code: str, file_path: str = "", max_attempts: int = 5) -> str:
        """Validate code and fix syntax errors with multiple retry attempts"""
        if not file_path.endswith('.py'):
            return code
        
        for attempt in range(max_attempts):
            try:
                # Try to parse the code
                ast.parse(code)
                if attempt > 0:
                    self.log(f"✅ Syntax validated for {file_path} after {attempt + 1} attempt(s)")
                return code
            except SyntaxError as e:
                error_msg = str(e.msg).lower() if e.msg else ""
                error_line = e.lineno if hasattr(e, 'lineno') and e.lineno else None
                
                # Apply specific fixes based on error type
                if 'expected an indented block' in error_msg or 'indented block' in error_msg:
                    code = self.fix_syntax_error(code, e, file_path)
                    code = self.fix_missing_indentation(code, file_path)
                elif 'invalid syntax' in error_msg:
                    # For invalid syntax, try more aggressive fixes
                    code = self.fix_syntax_error(code, e, file_path)
                    code = self.fix_all(code, file_path)
                    # Try to fix the specific line if we know it
                    if error_line:
                        code = self._fix_line_specific_syntax(code, error_line, file_path)
                else:
                    # Apply general fixes
                    code = self.fix_syntax_error(code, e, file_path)
                    code = self.fix_all(code, file_path)
                
                if attempt < max_attempts - 1:
                    continue
                else:
                    self.log(f"⚠️ Could not fully fix syntax in {file_path}: {str(e)}", level="warning")
        
        # Final attempt with comprehensive fixes
        try:
            code = self.fix_all(code, file_path)
            code = self.fix_missing_indentation(code, file_path)
            # Try one more aggressive fix pass
            code = self._aggressive_syntax_fix(code, file_path)
            ast.parse(code)
            self.log(f"✅ Syntax fixed for {file_path} with final comprehensive fix")
            return code
        except SyntaxError as e:
            self.log(f"⚠️ Syntax errors remain in {file_path} but proceeding: {str(e)}", level="warning")
            return code
    
    def fix_syntax_error(self, code: str, syntax_error: SyntaxError, file_path: str = "") -> str:
        """Fix specific syntax errors based on error message"""
        lines = code.split('\n')
        error_msg = str(syntax_error.msg).lower() if syntax_error.msg else ""
        
        # Get error line
        if hasattr(syntax_error, 'lineno') and syntax_error.lineno:
            error_line_idx = syntax_error.lineno - 1
            if 0 <= error_line_idx < len(lines):
                error_line = lines[error_line_idx]
                
                # Fix missing indentation after function/class definition
                if 'expected an indented block' in error_msg or 'indented block' in error_msg:
                    # Find the function/class definition that expects indentation
                    for i in range(error_line_idx, -1, -1):
                        if i < len(lines):
                            line = lines[i]
                            stripped = line.strip()
                            
                            # Check if this is a definition that expects indentation
                            if stripped.startswith(('def ', 'class ', 'if ', 'elif ', 'else:', 'for ', 'while ', 'with ', 'try:')):
                                if stripped.endswith(':'):
                                    # Check if next line is empty or not properly indented
                                    next_line_idx = i + 1
                                    if next_line_idx < len(lines):
                                        next_line = lines[next_line_idx]
                                        next_stripped = next_line.strip()
                                        
                                        # Calculate expected indentation
                                        base_indent = len(line) - len(line.lstrip())
                                        expected_indent = base_indent + 4
                                        
                                        # Check if next line is empty or not indented enough
                                        if not next_stripped or next_stripped.startswith('#'):
                                            # Empty line or comment - add pass
                                            lines.insert(next_line_idx, ' ' * expected_indent + 'pass')
                                            self.log(f"🔧 Added 'pass' statement after {file_path} line {i + 1}")
                                            return '\n'.join(lines)
                                        elif len(next_line) - len(next_line.lstrip()) <= base_indent:
                                            # Not indented enough - fix indentation
                                            lines[next_line_idx] = ' ' * expected_indent + next_stripped
                                            self.log(f"🔧 Fixed indentation in {file_path} line {next_line_idx + 1}")
                                            return '\n'.join(lines)
                                    else:
                                        # No next line - add pass
                                        base_indent = len(line) - len(line.lstrip())
                                        lines.append(' ' * (base_indent + 4) + 'pass')
                                        self.log(f"🔧 Added 'pass' statement at end of {file_path}")
                                        return '\n'.join(lines)
                                    break
                
                # Fix bracket mismatches
                if 'does not match' in error_msg or ('closing' in error_msg and 'opening' in error_msg):
                    return self.fix_bracket_mismatches(code, file_path)
                
                # Fix missing colons
                if 'expected' in error_msg and ':' in error_msg:
                    if any(keyword in error_line for keyword in ['def ', 'class ', 'if ', 'elif ', 'else', 'for ', 'while ', 'with ', 'try']):
                        if not error_line.rstrip().endswith(':'):
                            lines[error_line_idx] = error_line.rstrip() + ':'
                            self.log(f"🔧 Added missing colon in {file_path} line {syntax_error.lineno}")
                            return '\n'.join(lines)
        
        return code
    
    def fix_missing_indentation(self, code: str, file_path: str = "") -> str:
        """Fix missing indentation errors"""
        lines = code.split('\n')
        fixed_lines = []
        indent_stack = [0]
        indent_size = 4
        
        for i, line in enumerate(lines):
            stripped = line.lstrip()
            
            # Skip empty lines and comments
            if not stripped or stripped.startswith('#'):
                fixed_lines.append(line)
                continue
            
            current_indent = len(line) - len(stripped)
            
            # Check if previous line expects indentation
            if i > 0 and fixed_lines:
                prev_line = fixed_lines[-1].rstrip()
                if prev_line.endswith(':') and not prev_line.startswith('#'):
                    # Previous line ended with colon, this should be indented
                    expected_indent = indent_stack[-1] + indent_size
                    if expected_indent not in indent_stack:
                        indent_stack.append(expected_indent)
                else:
                    # Adjust indent stack
                    while len(indent_stack) > 1 and current_indent < indent_stack[-1]:
                        indent_stack.pop()
                    
                    if current_indent > indent_stack[-1]:
                        expected_indent = ((current_indent + indent_size - 1) // indent_size) * indent_size
                        if expected_indent not in indent_stack:
                            indent_stack.append(expected_indent)
            
            # Handle dedent keywords
            if stripped.startswith(('else:', 'elif ', 'except:', 'finally:')):
                if len(indent_stack) > 1:
                    indent_stack.pop()
            
            expected_indent = indent_stack[-1]
            
            # If line is not properly indented, fix it
            if current_indent != expected_indent:
                fixed_lines.append(' ' * expected_indent + stripped)
                if current_indent == 0 and expected_indent > 0:
                    self.log(f"🔧 Fixed missing indentation in {file_path} line {i + 1}")
            else:
                fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def fix_missing_colons(self, code: str, file_path: str = "") -> str:
        """Fix missing colons after function/class definitions"""
        lines = code.split('\n')
        fixed_lines = []
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            
            # Check for definitions that should end with colon
            if stripped and not stripped.startswith('#'):
                for keyword in ['def ', 'class ', 'if ', 'elif ', 'else', 'for ', 'while ', 'with ', 'try']:
                    if stripped.startswith(keyword) and not stripped.endswith(':'):
                        # Check if it's a complete statement (not a continuation)
                        if ':' not in stripped and not stripped.endswith('\\'):
                            fixed_lines.append(line.rstrip() + ':')
                            self.log(f"🔧 Added missing colon in {file_path} line {i + 1}")
                            break
                else:
                    fixed_lines.append(line)
            else:
                fixed_lines.append(line)
        
        return '\n'.join(fixed_lines)
    
    def fix_unterminated_string_literals(self, code: str, file_path: str = "") -> str:
        """Fix unterminated string literals in Python code"""
        lines = code.split('\n')
        fixed_lines = []
        in_string = False
        string_char = None
        escape_next = False
        triple_quote = False
        
        for line_num, line in enumerate(lines):
            fixed_line = ""
            i = 0
            
            while i < len(line):
                char = line[i]
                
                # Handle escape sequences
                if escape_next:
                    escape_next = False
                    fixed_line += char
                    i += 1
                    continue
                
                if char == '\\':
                    escape_next = True
                    fixed_line += char
                    i += 1
                    continue
                
                # Check for triple quotes
                if i < len(line) - 2:
                    triple = line[i:i+3]
                    if triple in ['"""', "'''"]:
                        if not in_string:
                            in_string = True
                            string_char = triple
                            triple_quote = True
                            fixed_line += triple
                            i += 3
                            continue
                        elif string_char == triple:
                            in_string = False
                            string_char = None
                            triple_quote = False
                            fixed_line += triple
                            i += 3
                            continue
                
                # Handle regular string quotes
                if not triple_quote and char in ['"', "'"]:
                    if not in_string:
                        in_string = True
                        string_char = char
                        fixed_line += char
                    elif char == string_char:
                        in_string = False
                        string_char = None
                        fixed_line += char
                    else:
                        fixed_line += char
                else:
                    fixed_line += char
                
                i += 1
            
            # If line ends while in string, close it
            if in_string:
                if triple_quote:
                    fixed_line += string_char
                    self.log(f"🔧 Fixed unterminated triple-quoted string in {file_path} line {line_num + 1}")
                else:
                    fixed_line += string_char
                    self.log(f"🔧 Fixed unterminated string literal in {file_path} line {line_num + 1}")
                in_string = False
                string_char = None
                triple_quote = False
            
            fixed_lines.append(fixed_line)
        
        return '\n'.join(fixed_lines)
    
    def fix_bracket_mismatches(self, code: str, file_path: str = "") -> str:
        """Fix bracket type mismatches (e.g., } instead of ))"""
        lines = code.split('\n')
        fixed_lines = []
        bracket_stack = []
        in_string = False
        string_char = None
        escape_next = False
        triple_quote = False
        
        for line_num, line in enumerate(lines):
            fixed_line = ""
            i = 0
            
            while i < len(line):
                char = line[i]
                
                # Handle escape sequences
                if escape_next:
                    escape_next = False
                    fixed_line += char
                    i += 1
                    continue
                
                if char == '\\':
                    escape_next = True
                    fixed_line += char
                    i += 1
                    continue
                
                # Check for triple quotes
                if i < len(line) - 2:
                    triple = line[i:i+3]
                    if triple in ['"""', "'''"]:
                        if not in_string:
                            in_string = True
                            string_char = triple
                            triple_quote = True
                            fixed_line += triple
                            i += 3
                            continue
                        elif string_char == triple:
                            in_string = False
                            string_char = None
                            triple_quote = False
                            fixed_line += triple
                            i += 3
                            continue
                
                # Handle regular string quotes
                if not triple_quote and char in ['"', "'"]:
                    if not in_string:
                        in_string = True
                        string_char = char
                        fixed_line += char
                    elif char == string_char:
                        in_string = False
                        string_char = None
                        fixed_line += char
                    else:
                        fixed_line += char
                elif not in_string:
                    # Process brackets only when not in string
                    if char == '(':
                        bracket_stack.append('(')
                        fixed_line += char
                    elif char == '[':
                        bracket_stack.append('[')
                        fixed_line += char
                    elif char == '{':
                        bracket_stack.append('{')
                        fixed_line += char
                    elif char == ')':
                        if bracket_stack and bracket_stack[-1] == '(':
                            bracket_stack.pop()
                            fixed_line += char
                        elif bracket_stack:
                            # Wrong bracket type
                            expected = bracket_stack.pop()
                            replacement = ')' if expected == '(' else ']' if expected == '[' else '}'
                            fixed_line += replacement
                            self.log(f"🔧 Fixed bracket mismatch in {file_path} line {line_num + 1}: replaced ')' with '{replacement}'")
                        else:
                            # Extra closing, skip it
                            self.log(f"🔧 Removed extra ')' in {file_path} line {line_num + 1}")
                    elif char == ']':
                        if bracket_stack and bracket_stack[-1] == '[':
                            bracket_stack.pop()
                            fixed_line += char
                        elif bracket_stack:
                            expected = bracket_stack.pop()
                            replacement = ')' if expected == '(' else ']' if expected == '[' else '}'
                            fixed_line += replacement
                            self.log(f"🔧 Fixed bracket mismatch in {file_path} line {line_num + 1}: replaced ']' with '{replacement}'")
                        else:
                            self.log(f"🔧 Removed extra ']' in {file_path} line {line_num + 1}")
                    elif char == '}':
                        if bracket_stack and bracket_stack[-1] == '{':
                            bracket_stack.pop()
                            fixed_line += char
                        elif bracket_stack:
                            expected = bracket_stack.pop()
                            replacement = ')' if expected == '(' else ']' if expected == '[' else '}'
                            fixed_line += replacement
                            self.log(f"🔧 Fixed bracket mismatch in {file_path} line {line_num + 1}: replaced '}}' with '{replacement}'")
                        else:
                            self.log(f"🔧 Removed extra '}}' in {file_path} line {line_num + 1}")
                    else:
                        fixed_line += char
                else:
                    fixed_line += char
                
                i += 1
            
            fixed_lines.append(fixed_line)
        
        return '\n'.join(fixed_lines)
    
    def fix_extra_closing_brackets(self, code: str, file_path: str = "") -> str:
        """Remove extra closing brackets"""
        open_parens, open_braces, open_curlies = self._count_brackets_accurate(code)
        
        if open_curlies < 0:
            excess = abs(open_curlies)
            code = self._remove_extra_closing_braces(code, excess, file_path)
        
        if open_braces < 0:
            excess = abs(open_braces)
            code = self._remove_extra_closing_brackets(code, excess, file_path)
        
        if open_parens < 0:
            excess = abs(open_parens)
            code = self._remove_extra_closing_parens(code, excess, file_path)
        
        return code
    
    def _count_brackets_accurate(self, code: str) -> tuple:
        """Count brackets accurately, accounting for strings and comments"""
        open_parens = 0
        open_braces = 0
        open_curlies = 0
        
        in_string = False
        string_char = None
        escape_next = False
        
        i = 0
        while i < len(code):
            char = code[i]
            
            # Handle comments
            if not in_string:
                if i < len(code) - 1 and code[i:i+2] == '//':
                    while i < len(code) and code[i] != '\n':
                        i += 1
                    continue
                elif i < len(code) - 1 and code[i:i+2] == '/*':
                    i += 2
                    while i < len(code) - 1:
                        if code[i:i+2] == '*/':
                            i += 2
                            break
                        i += 1
                    continue
                elif char == '#' and (i == 0 or code[i-1] in [' ', '\t', '\n']):
                    while i < len(code) and code[i] != '\n':
                        i += 1
                    continue
            
            # Handle strings
            if escape_next:
                escape_next = False
                i += 1
                continue
            
            if char == '\\':
                escape_next = True
                i += 1
                continue
            
            if char in ['"', "'"]:
                if not in_string:
                    in_string = True
                    string_char = char
                elif char == string_char:
                    in_string = False
                    string_char = None
                i += 1
                continue
            
            # Count brackets only when not in string
            if not in_string:
                if char == '(':
                    open_parens += 1
                elif char == ')':
                    open_parens -= 1
                elif char == '[':
                    open_braces += 1
                elif char == ']':
                    open_braces -= 1
                elif char == '{':
                    open_curlies += 1
                elif char == '}':
                    open_curlies -= 1
            
            i += 1
        
        return (open_curlies, open_braces, open_parens)
    
    def _remove_extra_closing_braces(self, code: str, count: int, file_path: str = "") -> str:
        """Remove extra closing braces"""
        lines = code.split('\n')
        removed = 0
        
        for line_idx in range(len(lines) - 1, -1, -1):
            if removed >= count:
                break
            
            line = lines[line_idx]
            brace_positions = [i for i, char in enumerate(line) if char == '}']
            
            for brace_pos in reversed(brace_positions):
                if removed >= count:
                    break
                
                quotes_before = line[:brace_pos].count('"') + line[:brace_pos].count("'")
                if quotes_before % 2 == 0:
                    lines[line_idx] = line[:brace_pos] + line[brace_pos+1:]
                    line = lines[line_idx]
                    removed += 1
                    self.log(f"🔧 Removed extra closing brace in {file_path} line {line_idx + 1}")
        
        return '\n'.join(lines)
    
    def _remove_extra_closing_brackets(self, code: str, count: int, file_path: str = "") -> str:
        """Remove extra closing brackets"""
        lines = code.split('\n')
        removed = 0
        
        for line_idx in range(len(lines) - 1, -1, -1):
            if removed >= count:
                break
            
            line = lines[line_idx]
            bracket_positions = [i for i, char in enumerate(line) if char == ']']
            
            for bracket_pos in reversed(bracket_positions):
                if removed >= count:
                    break
                
                quotes_before = line[:bracket_pos].count('"') + line[:bracket_pos].count("'")
                if quotes_before % 2 == 0:
                    lines[line_idx] = line[:bracket_pos] + line[bracket_pos+1:]
                    line = lines[line_idx]
                    removed += 1
                    self.log(f"🔧 Removed extra closing bracket in {file_path} line {line_idx + 1}")
        
        return '\n'.join(lines)
    
    def _remove_extra_closing_parens(self, code: str, count: int, file_path: str = "") -> str:
        """Remove extra closing parentheses"""
        lines = code.split('\n')
        removed = 0
        
        for line_idx in range(len(lines) - 1, -1, -1):
            if removed >= count:
                break
            
            line = lines[line_idx]
            paren_positions = [i for i, char in enumerate(line) if char == ')']
            
            for paren_pos in reversed(paren_positions):
                if removed >= count:
                    break
                
                quotes_before = line[:paren_pos].count('"') + line[:paren_pos].count("'")
                if quotes_before % 2 == 0:
                    lines[line_idx] = line[:paren_pos] + line[paren_pos+1:]
                    line = lines[line_idx]
                    removed += 1
                    self.log(f"🔧 Removed extra closing parenthesis in {file_path} line {line_idx + 1}")
        
        return '\n'.join(lines)
    
    def fix_json(self, json_str: str, file_path: str = "", error_msg: str = "") -> str:
        """Comprehensive JSON fixing utility"""
        import json
        
        # Try parsing first
        try:
            json.loads(json_str)
            return json_str
        except json.JSONDecodeError as e:
            if not error_msg:
                error_msg = str(e)
            
            # Apply fixes in order
            # Fix 1: Unterminated strings
            if "Unterminated string" in error_msg or "Unterminated" in error_msg:
                json_str = self._fix_json_unterminated_strings(json_str, file_path)
                try:
                    json.loads(json_str)
                    return json_str
                except json.JSONDecodeError:
                    pass
            
            # Fix 2: Property name issues (do this before comma fixes)
            if "property name" in error_msg.lower() or "enclosed in double quotes" in error_msg.lower():
                json_str = self._fix_json_property_names(json_str, file_path)
                try:
                    json.loads(json_str)
                    return json_str
                except json.JSONDecodeError:
                    pass
            
            # Fix 3: Missing commas
            if "Expecting ',' delimiter" in error_msg or "delimiter" in error_msg.lower():
                json_str = self._fix_json_missing_commas(json_str, file_path)
                try:
                    json.loads(json_str)
                    return json_str
                except json.JSONDecodeError:
                    pass
            
            # Fix 4: Missing closing braces/brackets
            open_braces = json_str.count('{') - json_str.count('}')
            open_brackets = json_str.count('[') - json_str.count(']')
            if open_braces > 0:
                json_str += '}' * open_braces
            if open_brackets > 0:
                json_str += ']' * open_brackets
            
            # Try one more time after all fixes
            try:
                json.loads(json_str)
                return json_str
            except json.JSONDecodeError:
                # Apply all fixes again in sequence
                json_str = self._fix_json_unterminated_strings(json_str, file_path)
                json_str = self._fix_json_property_names(json_str, file_path)
                json_str = self._fix_json_missing_commas(json_str, file_path)
                return json_str
    
    def _fix_json_unterminated_strings(self, json_str: str, file_path: str = "") -> str:
        """Fix unterminated strings in JSON"""
        result = []
        in_string = False
        escape_next = False
        i = 0
        
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
                if in_string:
                    # Check if this is the end of the string
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
    
    def _fix_json_missing_commas(self, json_str: str, file_path: str = "") -> str:
        """Fix missing commas in JSON using comprehensive approach"""
        import re
        
        try:
            fixed = json_str
            
            # Pattern 1: } or ] followed by "key" without comma
            fixed = re.sub(r'([}\]])"(\s*)"([^:]+)":', r'\1,\2"\3":', fixed)
            
            # Pattern 2: } or ] followed by { or [ without comma
            fixed = re.sub(r'([}\]])"(\s*)([{[])', r'\1,\2\3', fixed)
            
            # Pattern 3: "value" followed by "key" without comma
            fixed = re.sub(r'("(?:[^"\\]|\\.)*")\s*"([^:]+)":', r'\1, "\2":', fixed)
            
            # Pattern 4: number/boolean followed by "key" without comma
            fixed = re.sub(r'([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null)\s*"([^:]+)":', r'\1, "\2":', fixed)
            
            # Pattern 5: } or ] followed by "key" without comma (no whitespace)
            fixed = re.sub(r'([}\]])"([^:]+)":', r'\1, "\2":', fixed)
            
            # Pattern 6: "value" } or "value" ] without comma
            fixed = re.sub(r'("(?:[^"\\]|\\.)*")\s*([}\]])', r'\1, \2', fixed)
            
            # Pattern 7: number/boolean } or number/boolean ] without comma
            fixed = re.sub(r'([0-9]+(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?|true|false|null)\s*([}\]])', r'\1, \2', fixed)
            
            # Pattern 8: } or ] followed by number/boolean without comma
            fixed = re.sub(r'([}\]])"(\s*)([0-9]+|true|false|null)', r'\1, \2\3', fixed)
            
            # Pattern 9: } or ] followed by { or [ without comma
            fixed = re.sub(r'([}\]])"(\s*)([{[])', r'\1, \2\3', fixed)
            
            # Pattern 10: } or ] followed by whitespace and "key" (more flexible)
            fixed = re.sub(r'([}\]])"(\s+)"([^:]+)":', r'\1,\2"\3":', fixed)
            
            # Now use character-by-character approach for remaining issues
            fixed = self._fix_json_commas_char_by_char(fixed, file_path)
            
            return fixed
        except re.error as e:
            self.log(f"⚠️ Regex error in JSON comma fix: {str(e)}", level="warning")
            return self._fix_json_commas_char_by_char(json_str, file_path)
    
    def _fix_json_commas_char_by_char(self, json_str: str, file_path: str = "") -> str:
        """Fix missing commas character by character"""
        result = []
        i = 0
        in_string = False
        escape_next = False
        last_char = None
        last_value_end = None  # Track where last value ended
        in_number = False
        number_chars = set('0123456789.eE+-')
        
        while i < len(json_str):
            char = json_str[i]
            
            # Handle escape sequences
            if escape_next:
                escape_next = False
                result.append(char)
                last_char = char
                in_number = False
                i += 1
                continue
            
            if char == '\\':
                escape_next = True
                result.append(char)
                last_char = char
                in_number = False
                i += 1
                continue
            
            # Handle strings
            if char == '"':
                if not in_string:
                    in_string = True
                else:
                    in_string = False
                    last_value_end = len(result)  # Mark end of string value
                result.append(char)
                last_char = char
                in_number = False
                i += 1
                continue
            
            # Only process outside strings
            if not in_string:
                # Track if we're in a number
                if char in number_chars:
                    in_number = True
                elif char in [',', ':', '}', ']', '{', '[', ' ', '\t', '\n', '\r']:
                    in_number = False
                
                # Check if we need to add a comma
                # Case 1: } or ] followed by " (new key)
                if last_char in ['}', ']'] and char == '"':
                    # Look ahead to see if this is a key
                    lookahead = json_str[i:].lstrip()
                    if lookahead.startswith('"') and ':' in lookahead[:100]:
                        result.append(',')
                        self.log(f"🔧 Added missing comma after {last_char} in JSON")
                
                # Case 2: } or ] followed by { or [
                elif last_char in ['}', ']'] and char in ['{', '[']:
                    result.append(',')
                    self.log(f"🔧 Added missing comma after {last_char} in JSON")
                
                # Case 3: "value" followed by "key"
                elif last_char == '"' and char == '"' and last_value_end:
                    # Check if previous was end of value and this is start of key
                    lookahead = json_str[i:].lstrip()
                    if ':' in lookahead[:100]:
                        result.append(',')
                        self.log(f"🔧 Added missing comma between values in JSON")
                
                # Case 4: number/boolean followed by "key"
                elif (last_char in number_chars or last_char in ['e', 'l', 'u', 'r', 'a', 's', 'f', 't', 'n']) and char == '"':
                    # Check if we just finished a number or boolean
                    if not in_number or last_char in ['e', 'l', 'u', 'r', 'a', 's', 'f', 't', 'n']:
                        lookahead = json_str[i:].lstrip()
                        if ':' in lookahead[:100]:
                            result.append(',')
                            self.log(f"🔧 Added missing comma after value in JSON")
                
                # Case 5: } or ] followed by number/boolean
                elif last_char in ['}', ']'] and (char in number_chars or char in ['t', 'f', 'n']):
                    result.append(',')
                    self.log(f"🔧 Added missing comma after {last_char} in JSON")
                
                # Case 6: } or ] followed by whitespace then "key"
                elif last_char in ['}', ']'] and char in [' ', '\t', '\n', '\r']:
                    # Look ahead past whitespace
                    j = i + 1
                    while j < len(json_str) and json_str[j] in [' ', '\t', '\n', '\r']:
                        j += 1
                    if j < len(json_str) and json_str[j] == '"':
                        lookahead = json_str[j:].lstrip()
                        if ':' in lookahead[:100]:
                            result.append(',')
                            self.log(f"🔧 Added missing comma after {last_char} in JSON (with whitespace)")
            
            result.append(char)
            last_char = char
            i += 1
        
        return ''.join(result)
    
    def _fix_json_property_names(self, json_str: str, file_path: str = "") -> str:
        """Fix property names that aren't properly quoted"""
        import re
        
        # Fix unquoted property names
        # Pattern: { key: or , key: (missing quotes around key)
        fixed = re.sub(r'{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r'{"\1":', json_str)
        fixed = re.sub(r',\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*:', r', "\1":', fixed)
        
        # Fix property names with single quotes
        fixed = re.sub(r"'([^']+)'\s*:", r'"\1":', fixed)
        
        return fixed
    
    def _fix_line_specific_syntax(self, code: str, error_line: int, file_path: str = "") -> str:
        """Fix syntax errors on a specific line"""
        lines = code.split('\n')
        if error_line < 1 or error_line > len(lines):
            return code
        
        line_idx = error_line - 1
        line = lines[line_idx]
        
        # Common fixes for specific line issues
        # Fix 1: Remove trailing commas before colons
        if line.rstrip().endswith(',:'):
            lines[line_idx] = line.rstrip()[:-2] + ':'
            self.log(f"🔧 Fixed trailing comma before colon in {file_path} line {error_line}")
            return '\n'.join(lines)
        
        # Fix 2: Add missing colon
        stripped = line.strip()
        if stripped and not stripped.startswith('#') and not stripped.endswith(':'):
            for keyword in ['def ', 'class ', 'if ', 'elif ', 'else', 'for ', 'while ', 'with ', 'try']:
                if stripped.startswith(keyword) and ':' not in stripped:
                    lines[line_idx] = line.rstrip() + ':'
                    self.log(f"🔧 Added missing colon in {file_path} line {error_line}")
                    return '\n'.join(lines)
        
        # Fix 3: Remove duplicate operators
        if '===' in line or '!==' in line:
            lines[line_idx] = line.replace('===', '==').replace('!==', '!=')
            self.log(f"🔧 Fixed invalid operator in {file_path} line {error_line}")
            return '\n'.join(lines)
        
        # Fix 4: Fix unmatched quotes on the line
        single_quotes = line.count("'") - line.count("\\'")
        double_quotes = line.count('"') - line.count('\\"')
        if single_quotes % 2 != 0:
            lines[line_idx] = line + "'"
            self.log(f"🔧 Fixed unmatched single quote in {file_path} line {error_line}")
            return '\n'.join(lines)
        if double_quotes % 2 != 0:
            lines[line_idx] = line + '"'
            self.log(f"🔧 Fixed unmatched double quote in {file_path} line {error_line}")
            return '\n'.join(lines)
        
        return code
    
    def _aggressive_syntax_fix(self, code: str, file_path: str = "") -> str:
        """Apply aggressive syntax fixes as last resort"""
        lines = code.split('\n')
        fixed_lines = []
        
        for i, line in enumerate(lines):
            fixed_line = line
            
            # Remove any null bytes or invalid characters
            fixed_line = fixed_line.replace('\x00', '')
            
            # Fix common Python syntax issues
            # Remove duplicate colons
            if fixed_line.count('::') > 0:
                fixed_line = fixed_line.replace('::', ':')
            
            # Fix spacing around operators (be careful not to break strings)
            # Only fix if not in a string
            if '"' not in fixed_line and "'" not in fixed_line:
                fixed_line = re.sub(r'(\w+)([+\-*/=<>!]+)(\w+)', r'\1 \2 \3', fixed_line)
            
            # Remove trailing operators that shouldn't be there
            stripped = fixed_line.rstrip()
            if stripped and stripped[-1] in ('+', '-', '*', '/', '=', '<', '>', '!'):
                # Check if it's a valid operator (==, !=, <=, >=)
                if len(stripped) < 2 or not (stripped[-2:] in ['==', '!=', '<=', '>=']):
                    fixed_line = stripped[:-1].rstrip()
            
            fixed_lines.append(fixed_line)
        
        return '\n'.join(fixed_lines)
    
    def unescape_content(self, content: str) -> str:
        """Unescape escape sequences in content (\\n -> newline, etc.)"""
        return unescape_content(content)
    
    def validate_code_completeness(self, code: str, file_path: str = "") -> str:
        """Validate that code is complete and fix common truncation issues"""
        # Count unmatched brackets/braces/parentheses (accounting for strings and comments)
        open_parens, open_braces, open_curlies = self._count_brackets_accurate(code)
        
        # Check for incomplete function/class definitions
        if 'def ' in code or 'class ' in code:
            lines = code.split('\n')
            # Check if last non-empty line is incomplete
            last_line = None
            for line in reversed(lines):
                stripped = line.strip()
                if stripped and not stripped.startswith('#'):
                    last_line = stripped
                    break
            
            # If last line doesn't end properly, might be truncated
            if last_line and not last_line.endswith((':', ';', '}', ']', ')')):
                # Check if it's a function/class definition that should end with colon
                if last_line.startswith(('def ', 'class ', 'if ', 'elif ', 'else:', 'for ', 'while ', 'with ', 'try:')):
                    if not last_line.endswith(':'):
                        code += '\n    pass  # TODO: Complete implementation'
                        self.log(f"⚠️ Added placeholder for incomplete code in {file_path}")
        
        # Fix unclosed structures (only add if we have more opening than closing)
        if open_curlies > 0:
            code += '\n' + '}' * open_curlies
            self.log(f"⚠️ Added {open_curlies} closing braces in {file_path}")
        if open_braces > 0:
            code += '\n' + ']' * open_braces
            self.log(f"⚠️ Added {open_braces} closing brackets in {file_path}")
        if open_parens > 0:
            code += '\n' + ')' * open_parens
            self.log(f"⚠️ Added {open_parens} closing parentheses in {file_path}")
        
        return code
    
    def format_code_files(self, code_files: dict, file_path_key: str = "") -> dict:
        """
        Format and validate multiple code files.
        
        Args:
            code_files: Dictionary mapping file paths to file contents
            file_path_key: Optional key to extract file path from (if code_files values are dicts)
            
        Returns:
            Dictionary with formatted and validated file contents
        """
        from typing import Dict
        
        fixed_code = {}
        code_file_extensions = ['.py', '.js', '.ts', '.jsx', '.tsx', '.java', '.go', '.rs']
        
        for file_path, content in code_files.items():
            # Skip non-code files (pass through as-is)
            if not any(file_path.endswith(ext) for ext in code_file_extensions):
                fixed_code[file_path] = content
                continue
            
            # Process code files
            if isinstance(content, str):
                # Unescape content (handle \n, \t, etc.)
                content = self.unescape_content(content)
                
                # Fix Python files specifically
                if file_path.endswith('.py'):
                    content = self.fix_all(content, file_path)
                    content = self.validate_code_completeness(content, file_path)
                    content = self.validate_and_fix(content, file_path, max_attempts=5)
            
            fixed_code[file_path] = content
        
        return fixed_code