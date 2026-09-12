from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(".env", "../.env"),
        extra="ignore",
    )

    database_url: str = "postgresql+asyncpg://portfel:portfel@localhost:5432/portfel"
    app_username: str = "admin"
    app_password: str = "changeme"
    session_secret: str = "dev-session-secret-change-me-32chars"
    fernet_key: str = ""
    cookie_secure: bool = False
    session_cookie_name: str = "portfel_session"
    session_max_age: int = 7 * 24 * 60 * 60
    cors_origins: str = "http://localhost:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [item.strip() for item in self.cors_origins.split(",") if item.strip()]


settings = Settings()
