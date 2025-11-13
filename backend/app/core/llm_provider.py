"""LLM provider abstraction layer for supporting multiple AI providers."""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
import time
from openai import OpenAI
from app.core.config import settings
from app.core.logger import log_llm_call

class LLMProvider(ABC):
    """Abstract base class for LLM providers."""
    
    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> str:
        """Generate a chat completion."""
        pass
    
    @abstractmethod
    def get_provider_name(self) -> str:
        """Return the provider name."""
        pass

class OpenAIProvider(LLMProvider):
    """OpenAI API provider."""
    
    def __init__(self, api_key: str, model: str = "gpt-4o-mini"):
        self.client = OpenAI(api_key=api_key)
        self.model = model
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> str:
        """Generate a chat completion using OpenAI."""
        start_time = time.time()
        
        try:
            params = {
                "model": self.model,
                "messages": messages,
                "temperature": temperature,
                **kwargs
            }
            
            if response_format:
                params["response_format"] = response_format
            
            response = self.client.chat.completions.create(**params)
            
            duration_ms = int((time.time() - start_time) * 1000)
            tokens = response.usage.total_tokens if hasattr(response, 'usage') else None
            
            log_llm_call(
                provider="openai",
                model=self.model,
                tokens=tokens,
                duration_ms=duration_ms,
                status="success"
            )
            
            return response.choices[0].message.content
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            log_llm_call(
                provider="openai",
                model=self.model,
                duration_ms=duration_ms,
                status="error",
                error=str(e)
            )
            raise

    def get_provider_name(self) -> str:
        return "openai"

class AnthropicProvider(LLMProvider):
    """Anthropic (Claude) API provider."""
    
    def __init__(self, api_key: str, model: str = "claude-3-sonnet-20240229"):
        try:
            import anthropic
            self.client = anthropic.Anthropic(api_key=api_key)
            self.model = model
        except ImportError:
            raise ImportError("anthropic package not installed. Run: pip install anthropic")
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> str:
        """Generate a chat completion using Anthropic."""
        start_time = time.time()
        
        try:
            # Convert OpenAI-style messages to Anthropic format
            system_message = None
            anthropic_messages = []
            
            for msg in messages:
                if msg["role"] == "system":
                    system_message = msg["content"]
                else:
                    anthropic_messages.append({
                        "role": msg["role"],
                        "content": msg["content"]
                    })
            
            params = {
                "model": self.model,
                "messages": anthropic_messages,
                "temperature": temperature,
                "max_tokens": kwargs.get("max_tokens", 4096),
            }
            
            if system_message:
                params["system"] = system_message
            
            response = self.client.messages.create(**params)
            
            duration_ms = int((time.time() - start_time) * 1000)
            tokens = response.usage.input_tokens + response.usage.output_tokens if hasattr(response, 'usage') else None
            
            log_llm_call(
                provider="anthropic",
                model=self.model,
                tokens=tokens,
                duration_ms=duration_ms,
                status="success"
            )
            
            return response.content[0].text
            
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            log_llm_call(
                provider="anthropic",
                model=self.model,
                duration_ms=duration_ms,
                status="error",
                error=str(e)
            )
            raise
    
    def get_provider_name(self) -> str:
        return "anthropic"

class LocalLLMProvider(LLMProvider):
    """Local LLM provider (using Ollama or similar)."""
    
    def __init__(self, base_url: str = "http://localhost:11434", model: str = "llama2"):
        self.base_url = base_url
        self.model = model
    
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        response_format: Optional[Dict] = None,
        **kwargs
    ) -> str:
        """Generate a chat completion using local LLM."""
        import httpx
        start_time = time.time()
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/api/chat",
                    json={
                        "model": self.model,
                        "messages": messages,
                        "stream": False,
                        "options": {
                            "temperature": temperature
                        }
                    },
                    timeout=120.0
                )
                response.raise_for_status()
                result = response.json()
                
                duration_ms = int((time.time() - start_time) * 1000)
                
                log_llm_call(
                    provider="local",
                    model=self.model,
                    duration_ms=duration_ms,
                    status="success"
                )
                
                return result["message"]["content"]
                
        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            log_llm_call(
                provider="local",
                model=self.model,
                duration_ms=duration_ms,
                status="error",
                error=str(e)
            )
            raise
    
    def get_provider_name(self) -> str:
        return "local"

def get_llm_provider() -> LLMProvider:
    """
    Factory function to get the configured LLM provider.
    
    Returns:
        Configured LLM provider instance
    """
    provider_name = settings.llm_provider.lower()
    
    if provider_name == "openai":
        if not settings.openai_api_key:
            raise ValueError("OPENAI_API_KEY not configured")
        return OpenAIProvider(
            api_key=settings.openai_api_key,
            model=settings.openai_model
        )
    
    elif provider_name == "anthropic":
        if not settings.anthropic_api_key:
            raise ValueError("ANTHROPIC_API_KEY not configured")
        return AnthropicProvider(
            api_key=settings.anthropic_api_key,
            model=settings.anthropic_model
        )
    
    elif provider_name == "local":
        return LocalLLMProvider(
            base_url=settings.local_llm_url,
            model=settings.local_llm_model
        )
    
    else:
        raise ValueError(f"Unknown LLM provider: {provider_name}. Supported: openai, anthropic, local")

# Global provider instance
llm_provider = None

def init_llm_provider():
    """Initialize the global LLM provider."""
    global llm_provider
    llm_provider = get_llm_provider()
    return llm_provider

