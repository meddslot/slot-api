from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

# Load .env before the Settings singleton is constructed so the file
# always wins over any system-level environment variable.
load_dotenv(override=True)


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    postgres_user: str
    postgres_password: str
    postgres_db: str
    database_url: str


settings = Settings()
