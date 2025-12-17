"""
Unified LLM Manager - Configuration, Factory, and Fallback Wrapper
Consolidates LLMConfig, LLMFactory, and LLMWithFallback into a single efficient module.

PRIMARY: Ollama (local) - Qwen2.5 Coder 7B
FALLBACK: OpenRouter / Groq (if Ollama not available)
Also supports OpenAI and Anthropic when explicitly provided.
"""

import os
from typing import Optional, Any, List, Dict
from dataclasses import dataclass, field
from langchain_core.messages import BaseMessage
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_groq import ChatGroq

# Try to import Ollama - fallback gracefully if not available
_ollama_available = False
ChatOllama = None
try:
    from langchain_ollama import ChatOllama
    _ollama_available = True
except ImportError:
    try:
        from langchain_community.chat_models import ChatOllama
        _ollama_available = True
    except ImportError:
        pass


@dataclass
class LLMConfig:
    """LLM provider and model configuration"""
    
    # API Keys (from environment)
    openrouter_api_key: Optional[str] = field(default=None, init=False)
    groq_api_key: Optional[str] = field(default=None, init=False)
    openai_api_key: Optional[str] = field(default=None, init=False)
    anthropic_api_key: Optional[str] = field(default=None, init=False)
    
    # Primary provider (Ollama - local)
    primary_provider: str = "ollama"
    primary_model: str = "qwen2.5-coder:7b"
    ollama_base_url: str = "http://localhost:11434"
    
    # Fallback providers
    fallback_provider: str = "openrouter"
    fallback_model: str = "openai/gpt-4o"
    
    # Model selection for free tier
    use_free_tier_model: bool = field(default=False, init=False)
    free_tier_model: str = "meta-llama/llama-3.1-70b-instruct"
    
    # Token limits
    max_tokens: int = field(default=1500, init=False)
    fallback_max_tokens: int = field(default=4000, init=False)
    
    # Request settings
    temperature: float = 0.7
    timeout: int = field(default=120, init=False)
    
    # Retry settings
    max_retries: int = 3
    retry_delay: float = 1.0
    
    # OpenRouter model options
    openrouter_models: dict = field(default_factory=lambda: {
        "openai/gpt-4o": "GPT-4 Omni - Latest and most capable (recommended)",
        "openai/gpt-4-turbo": "GPT-4 Turbo - Fast and capable",
        "anthropic/claude-3.5-sonnet": "Claude 3.5 Sonnet - Excellent reasoning",
        "google/gemini-pro-1.5": "Gemini Pro 1.5 - Great for code generation",
        "meta-llama/llama-3.1-70b-instruct": "Llama 3.1 70B - Open source powerhouse",
        "mistralai/mixtral-8x7b-instruct": "Mixtral 8x7B - Fast and efficient",
    })
    
    def __post_init__(self):
        """Load API keys and settings from environment"""
        self.openrouter_api_key = os.getenv("OPENROUTER_API_KEY")
        self.groq_api_key = os.getenv("GROQ_API_KEY")
        self.openai_api_key = os.getenv("OPENAI_API_KEY")
        self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY")
        
        self.use_free_tier_model = os.getenv("USE_FREE_TIER_MODEL", "false").lower() == "true"
        self.max_tokens = int(os.getenv("MAX_TOKENS", "1500"))
        self.fallback_max_tokens = int(os.getenv("FALLBACK_MAX_TOKENS", "4000"))
        self.timeout = int(os.getenv("LLM_TIMEOUT", "120"))
        self.max_retries = int(os.getenv("LLM_MAX_RETRIES", "3"))
        
        if os.getenv("PRIMARY_MODEL"):
            self.primary_model = os.getenv("PRIMARY_MODEL")
        if os.getenv("FALLBACK_MODEL"):
            self.fallback_model = os.getenv("FALLBACK_MODEL")
        if os.getenv("OLLAMA_BASE_URL"):
            self.ollama_base_url = os.getenv("OLLAMA_BASE_URL")
        if os.getenv("OLLAMA_MODEL"):
            self.primary_model = os.getenv("OLLAMA_MODEL")
    
    def get_active_model(self) -> str:
        """Get the active model based on configuration"""
        return self.free_tier_model if self.use_free_tier_model else self.primary_model


class LLMFactory:
    """Factory for creating LLM instances with multiple providers"""
    
    # Ollama configuration
    OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
    OLLAMA_DEFAULT_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5-coder:7b")
    
    # Lazy-loaded config instance
    _config: Optional[LLMConfig] = None
    
    @classmethod
    def _get_config(cls) -> LLMConfig:
        """Get or create config instance (lazy loading)"""
        if cls._config is None:
            cls._config = LLMConfig()
        return cls._config
    
    @staticmethod
    def _create_ollama_llm(model: Optional[str] = None, base_url: Optional[str] = None):
        """Create an LLM that talks to local Ollama"""
        if not _ollama_available:
            raise ImportError("Ollama is not available. Install it with: pip install langchain-ollama")
        
        config = LLMFactory._get_config()
        selected_model = model or LLMFactory.OLLAMA_DEFAULT_MODEL
        selected_base_url = base_url or LLMFactory.OLLAMA_BASE_URL
        
        return ChatOllama(
            model=selected_model,
            base_url=selected_base_url,
            temperature=config.temperature,
            num_ctx=4096,  # Input context window
            timeout=config.timeout,
        )
    
    @staticmethod
    def _create_openrouter_llm(api_key: str, model: Optional[str] = None):
        """Create an LLM that talks to OpenRouter"""
        config = LLMFactory._get_config()
        default_model = model or config.primary_model
        
        # Use free tier model if enabled and no explicit model
        if not model and config.use_free_tier_model and default_model == config.primary_model:
            default_model = config.free_tier_model
        
        return ChatOpenAI(
            model=default_model,
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
            default_headers={
                "HTTP-Referer": "https://github.com/your-repo",
                "X-Title": "FigmaToFullApp",
            },
            temperature=config.temperature,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
        )
    
    @staticmethod
    def _create_groq_llm(api_key: str, model: Optional[str] = None):
        """Create an LLM that talks to Groq"""
        config = LLMFactory._get_config()
        selected_model = model or config.fallback_model
        
        # Safety check: avoid decommissioned models
        if selected_model == "llama-3.1-70b-versatile":
            selected_model = config.fallback_model
        
        return ChatGroq(
            model=selected_model,
            api_key=api_key,
            temperature=config.temperature,
            max_tokens=config.fallback_max_tokens,
            timeout=config.timeout,
        )
    
    @staticmethod
    def create_llm(api_key: Optional[str] = None, model: Optional[str] = None) -> Any:
        """
        Create an LLM instance with Ollama as PRIMARY, OpenRouter/Groq as FALLBACK.
        
        Priority order:
        1. Ollama (local) - if available and USE_OLLAMA is true
        2. Explicit OpenRouter key (if provided)
        3. Environment OPENROUTER_API_KEY
        4. Explicit Groq key (if provided)
        5. Environment GROQ_API_KEY
        """
        use_ollama = os.getenv("USE_OLLAMA", "true").lower() == "true"
        ollama_model = os.getenv("OLLAMA_MODEL", LLMFactory.OLLAMA_DEFAULT_MODEL)
        env_openrouter_key = os.getenv("OPENROUTER_API_KEY")
        env_groq_key = os.getenv("GROQ_API_KEY")
        
        # Priority 1: Try Ollama if enabled
        if use_ollama and _ollama_available:
            try:
                selected_model = model or ollama_model
                return LLMFactory._create_ollama_llm(model=selected_model)
            except Exception as e:
                print(f"Warning: Ollama not available, falling back: {e}")
        
        # If explicit API key provided, detect type
        if api_key:
            api_key = api_key.strip()
            
            if api_key.startswith("sk-or-v1-") or (api_key.startswith("sk-") and len(api_key) > 100):
                return LLMFactory._create_openrouter_llm(api_key, model)
            
            if api_key.startswith("gsk_"):
                if env_openrouter_key:
                    return LLMFactory._create_openrouter_llm(env_openrouter_key, model)
                return LLMFactory._create_groq_llm(api_key, model)
            
            if api_key.startswith("sk-") and len(api_key) < 60:
                config = LLMFactory._get_config()
                return ChatOpenAI(
                    model=model or "gpt-4-turbo-preview",
                    api_key=api_key,
                    temperature=config.temperature,
                )
            
            if api_key.startswith("sk-ant-"):
                config = LLMFactory._get_config()
                return ChatAnthropic(
                    model=model or "claude-3-5-sonnet-20241022",
                    api_key=api_key,
                    temperature=config.temperature,
                )
            
            return LLMFactory._create_openrouter_llm(api_key, model)
        
        # No explicit key -> PRIMARY: OpenRouter, FALLBACK: Groq
        if env_openrouter_key:
            return LLMFactory._create_openrouter_llm(env_openrouter_key, model)
        
        if env_groq_key:
            return LLMFactory._create_groq_llm(env_groq_key, model)
        
        # Last resort: Try Ollama even if not explicitly enabled
        if _ollama_available:
            try:
                selected_model = model or ollama_model
                return LLMFactory._create_ollama_llm(model=selected_model)
            except Exception:
                pass
        
        # Final error
        error_msg = "No LLM available! "
        if not _ollama_available:
            error_msg += "Ollama not installed (pip install langchain-ollama). "
        if not env_openrouter_key and not env_groq_key and not api_key:
            error_msg += "Please set OPENROUTER_API_KEY, GROQ_API_KEY, or ensure Ollama is running."
        raise ValueError(error_msg)
    
    @staticmethod
    def get_models() -> Dict[str, str]:
        """Get available OpenRouter models (for UI display)"""
        return LLMFactory._get_config().openrouter_models


class LLMWithFallback:
    """
    LLM wrapper that automatically falls back to OpenRouter/Groq if Ollama fails.
    Handles connection errors, timeout errors, and other API errors.
    """
    
    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None):
        self.api_key = api_key
        self.model = model
        self.primary_llm = None
        self.fallback_llm = None
        self.using_fallback = False
        self._initialize_llms()
    
    def _initialize_llms(self):
        """Initialize primary (Ollama) and fallback (OpenRouter/Groq) LLMs"""
        use_ollama = os.getenv("USE_OLLAMA", "true").lower() == "true"
        ollama_model = os.getenv("OLLAMA_MODEL", LLMFactory.OLLAMA_DEFAULT_MODEL)
        env_openrouter_key = os.getenv("OPENROUTER_API_KEY")
        env_groq_key = os.getenv("GROQ_API_KEY")
        
        # Initialize primary LLM (Ollama)
        try:
            if use_ollama:
                selected_model = self.model or ollama_model
                self.primary_llm = LLMFactory._create_ollama_llm(model=selected_model)
        except Exception:
            self.primary_llm = None
        
        # Initialize fallback LLM (OpenRouter or Groq)
        try:
            if env_openrouter_key or (self.api_key and (self.api_key.startswith("sk-or-v1-") or (self.api_key.startswith("sk-") and len(self.api_key) > 100))):
                api_key_to_use = self.api_key if self.api_key and self.api_key.startswith(("sk-or-v1-", "sk-")) else env_openrouter_key
                self.fallback_llm = LLMFactory._create_openrouter_llm(api_key_to_use, self.model)
            elif env_groq_key or (self.api_key and self.api_key.startswith("gsk_")):
                api_key_to_use = self.api_key if self.api_key and self.api_key.startswith("gsk_") else env_groq_key
                self.fallback_llm = LLMFactory._create_groq_llm(api_key_to_use, self.model)
        except Exception:
            self.fallback_llm = None
    
    def _should_fallback(self, error: Exception) -> bool:
        """Determine if we should fall back based on the error"""
        error_str = str(error).lower()
        fallback_indicators = [
            "402", "401", "429",  # HTTP error codes
            "requires more credits", "can only afford", "insufficient credits",
            "invalid_api_key", "rate limit",
        ]
        return any(indicator in error_str for indicator in fallback_indicators)
    
    def invoke(self, messages: List[BaseMessage], **kwargs) -> Any:
        """Invoke LLM with automatic fallback to OpenRouter/Groq if Ollama fails"""
        # Try primary LLM first (Ollama)
        if self.primary_llm and not self.using_fallback:
            try:
                invoke_kwargs = kwargs.copy()
                if 'max_tokens' in invoke_kwargs:
                    del invoke_kwargs['max_tokens']  # Ollama doesn't accept this
                
                return self.primary_llm.invoke(messages, **invoke_kwargs)
            except Exception as e:
                if self._should_fallback(e) and self.fallback_llm:
                    self.using_fallback = True
                    try:
                        return self.fallback_llm.invoke(messages, **kwargs)
                    except Exception:
                        raise e
                raise e
        
        # If already using fallback or no primary LLM, use fallback directly
        if self.fallback_llm:
            return self.fallback_llm.invoke(messages, **kwargs)
        
        # No LLMs available
        error_msg = "No LLM available. "
        if not self.primary_llm:
            error_msg += "Ollama not running (ensure Ollama is installed and running: ollama serve). "
        if not self.fallback_llm:
            error_msg += "Or set OPENROUTER_API_KEY or GROQ_API_KEY in your .env file."
        raise ValueError(error_msg)
    
    def __getattr__(self, name):
        """Delegate other method calls to the active LLM"""
        active_llm = self.fallback_llm if self.using_fallback else self.primary_llm
        if active_llm is None:
            active_llm = self.fallback_llm or self.primary_llm
        
        if active_llm is None:
            raise AttributeError(f"'{self.__class__.__name__}' object has no attribute '{name}'")
        
        return getattr(active_llm, name)



