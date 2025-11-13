from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    # LLM Provider Configuration
    llm_provider: str = "openai"  # openai, anthropic, local
    
    # OpenAI Configuration
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    
    # Anthropic Configuration
    anthropic_api_key: str = ""
    anthropic_model: str = "claude-3-sonnet-20240229"
    
    # Local LLM Configuration
    local_llm_url: str = "http://localhost:11434"
    local_llm_model: str = "llama2"
    
    # Server Configuration
    host: str = "0.0.0.0"
    port: int = 8000
    
    # Browser Configuration
    headless: bool = True
    browser_timeout: int = 30000
    
    # Logging Configuration
    log_level: str = "INFO"
    log_file: str = "logs/app.log"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Also check environment variables directly (for cases where .env isn't loaded)
        if not self.openai_api_key:
            self.openai_api_key = os.getenv("OPENAI_API_KEY", os.getenv("openai_api_key", ""))
        if not self.anthropic_api_key:
            self.anthropic_api_key = os.getenv("ANTHROPIC_API_KEY", os.getenv("anthropic_api_key", ""))

settings = Settings()

