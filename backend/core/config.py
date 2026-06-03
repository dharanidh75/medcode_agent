from pydantic_settings import BaseSettings
from typing import List
import json


class Settings(BaseSettings):
    # LLM
    GROQ_API_KEY: str
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    # Database
    DATABASE_PUBLIC_URL: str

    # ChromaDB
    CHROMA_PERSIST_DIR: str = "./chroma_store"

    # App
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    MAX_AGENT_RETRIES: int = 3

    # CORS
    CORS_ORIGINS: str = '["http://localhost:5173","http://localhost:3000"]'

    def get_cors_origins(self) -> List[str]:
        return json.loads(self.CORS_ORIGINS)

    class Config:
        env_file = ".env"
        extra = "ignore"


settings = Settings()