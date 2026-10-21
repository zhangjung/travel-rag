from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parents[2]


class Settings(BaseSettings):
    """Runtime configuration. Live requirements are validated explicitly."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    app_mode: Literal["mock", "live"] = "mock"
    log_level: str = "INFO"
    log_dir: Path = PROJECT_ROOT / "logs"

    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com/v1"
    research_model: str = "deepseek-v4-flash"
    planner_model: str = "deepseek-v4-pro"
    reviewer_model: str = "deepseek-v4-pro"
    research_max_tokens: int = Field(default=8192, ge=1024, le=65536)
    planner_max_tokens: int = Field(default=8192, ge=1024, le=65536)
    reviewer_max_tokens: int = Field(default=4096, ge=1024, le=65536)
    tavily_api_key: SecretStr | None = None

    embedding_model: str = "BAAI/bge-small-zh-v1.5"
    embedding_revision: str = "7999e1d3359715c523056ef9478215996d62a620"
    reranker_model: str = "BAAI/bge-reranker-base"
    reranker_revision: str = "2cfc18c9415c912f9d8155881c133215df768a70"
    embedding_device: Literal["cuda"] = "cuda"
    reranker_device: Literal["cuda"] = "cuda"
    model_local_files_only: bool = True
    hf_home: Path = Path("D:/Anaconda_envs/pkgs/travel-rag/.cache/huggingface")
    torch_home: Path = Path("D:/Anaconda_envs/pkgs/travel-rag/.cache/torch")
    chroma_dir: Path = PROJECT_ROOT / "data" / "index" / "chroma"
    knowledge_source_dir: Path = PROJECT_ROOT / "data" / "demo"
    plans_db_path: Path = PROJECT_ROOT / "data" / "user" / "travel-rag.sqlite3"
    retrieval_top_k: int = Field(default=8, ge=1, le=50)
    rerank_top_n: int = Field(default=4, ge=1, le=20)
    local_confidence_threshold: float = Field(default=0.55, ge=0, le=1)

    @model_validator(mode="after")
    def resolve_relative_paths(self) -> Settings:
        if not self.log_dir.is_absolute():
            self.log_dir = PROJECT_ROOT / self.log_dir
        if not self.chroma_dir.is_absolute():
            self.chroma_dir = PROJECT_ROOT / self.chroma_dir
        if not self.knowledge_source_dir.is_absolute():
            self.knowledge_source_dir = PROJECT_ROOT / self.knowledge_source_dir
        if not self.plans_db_path.is_absolute():
            self.plans_db_path = PROJECT_ROOT / self.plans_db_path
        if not self.hf_home.is_absolute():
            self.hf_home = PROJECT_ROOT / self.hf_home
        if not self.torch_home.is_absolute():
            self.torch_home = PROJECT_ROOT / self.torch_home
        return self

    def validate_live(self) -> None:
        missing: list[str] = []
        if not self.deepseek_api_key or not self.deepseek_api_key.get_secret_value():
            missing.append("DEEPSEEK_API_KEY")
        if not self.tavily_api_key or not self.tavily_api_key.get_secret_value():
            missing.append("TAVILY_API_KEY")
        if missing:
            raise RuntimeError(f"Live 模式缺少必要配置：{', '.join(missing)}")


@lru_cache
def get_settings() -> Settings:
    return Settings()
