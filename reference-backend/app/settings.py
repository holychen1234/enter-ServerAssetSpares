from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    mysql_host: str = "mysql"
    mysql_port: int = 3306
    mysql_user: str = "cmdb"
    mysql_password: str = "cmdb123"
    mysql_database: str = "cmdb"

    jwt_secret: str = "change-me"
    jwt_alg: str = "HS256"
    jwt_ttl_hours: int = 12

    cors_origins: str = "http://localhost:5173"

    redfish_default_base: str = "http://redfish-mock:8000"
    redfish_timeout_seconds: int = 60  # per-request timeout; slow BMCs (Dell iDRAC, XFusion) need more headroom

    poll_interval_seconds: int = 86400  # 24 hours — hardware data changes rarely

    ai_api_key: str = ""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    @property
    def db_url(self) -> str:
        return (
            f"mysql+pymysql://{self.mysql_user}:{self.mysql_password}"
            f"@{self.mysql_host}:{self.mysql_port}/{self.mysql_database}"
            "?charset=utf8mb4"
        )

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()
