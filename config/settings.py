from pydantic_settings import BaseSettings, SettingsConfigDict
from pathlib import Path


class Settings(BaseSettings):
    groq_api_key: str = ""
    telegram_bot_token: str = ""
    gmail_credentials_path: str = "data/gmail_creds.json"
    faiss_index_path: str = "data/faiss_index"
    embed_model: str = "all-MiniLM-L6-v2"
    top_k_chunks: int = 4
    poll_interval: int = 5

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
    )


settings = Settings()
