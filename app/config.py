from functools import lru_cache
from pathlib import Path
from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "Gen AI Incident Management Assistant"
    data_dir: Path = Field(default=Path("data"), validation_alias="DATA_DIR")
    database_path: Path | None = Field(default=None, validation_alias="DATABASE_PATH")
    incidents_dir: Path | None = Field(default=None, validation_alias="INCIDENTS_DIR")
    openai_api_key: str | None = Field(default=None, validation_alias="OPENAI_API_KEY")
    openai_model: str = Field(default="gpt-4o-mini", validation_alias="OPENAI_MODEL")
    realtime_model: str = Field(default="gpt-realtime", validation_alias="OPENAI_REALTIME_MODEL")
    realtime_voice: str = Field(default="marin", validation_alias="OPENAI_REALTIME_VOICE")
    embedding_model: str = Field(default="text-embedding-3-small", validation_alias="OPENAI_EMBEDDING_MODEL")
    embedding_dimensions: int = Field(default=256, validation_alias="EMBEDDING_DIMENSIONS")
    use_openai_embeddings: bool = Field(default=False, validation_alias="USE_OPENAI_EMBEDDINGS")
    enable_external_search: bool = Field(default=True, validation_alias="ENABLE_EXTERNAL_SEARCH")

    @field_validator("openai_api_key")
    @classmethod
    def normalize_placeholder_api_key(cls, value: str | None) -> str | None:
        if not value or value.strip() in {"", "your_openai_api_key_here"}:
            return None
        return value

    @property
    def resolved_database_path(self) -> Path:
        return self.database_path or self.data_dir / "assistant.db"

    @property
    def resolved_incidents_dir(self) -> Path:
        return self.incidents_dir or self.data_dir / "incidents"


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.data_dir.mkdir(parents=True, exist_ok=True)
    settings.resolved_incidents_dir.mkdir(parents=True, exist_ok=True)
    return settings
