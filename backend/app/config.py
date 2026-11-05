from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./data/videomind.db"
    redis_url: str = ""

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    deepseek_model: str = "deepseek-chat"

    asr_engine: str = "mock"
    ocr_engine: str = "none"
    output_schemas: str = "summary,uml_draft,key_points,code_blocks"
    # F5 语音-视觉交叉校验：课程版只做设计，默认关闭（docs/产品定义.md §五）
    asr_vocabulary_crosscheck: bool = False

    media_root: str = "./data/media"
    cache_root: str = "./data/cache"

    cors_origins: str = "http://localhost:5173"

    @property
    def output_schema_list(self) -> list[str]:
        return [s.strip() for s in self.output_schemas.split(",") if s.strip()]

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()
