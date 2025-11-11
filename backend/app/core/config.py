from pydantic_settings import BaseSettings
import os

class Settings(BaseSettings):
    openai_api_key: str = ""
    openai_model: str = "gpt-4o-mini"
    
    class Config:
        env_file = ".env"
        case_sensitive = False

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        # Also check environment variables directly (for cases where .env isn't loaded)
        if not self.openai_api_key:
            self.openai_api_key = os.getenv("OPENAI_API_KEY", os.getenv("openai_api_key", ""))

settings = Settings()

