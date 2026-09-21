"""
Settings management with YAML config, environment variable overrides, and validation.
"""
import os
import yaml
from pathlib import Path
from typing import Any, Dict, Optional, List
from dataclasses import dataclass, field, asdict
from pydantic import BaseModel, Field
from pydantic_settings import BaseSettings


class LLMSettings(BaseModel):
    """LLM configuration"""
    backend: str = "auto"  # auto, ollama, openai-compatible, nvidia-nim, mock
    model: Optional[str] = None
    temperature: float = 0.7
    max_tokens: int = 2048
    ollama_base_url: str = "http://localhost:11434"
    openai_base_url: str = "http://localhost:1234/v1"
    openai_api_key: str = "not-needed"
    nvidia_api_key: Optional[str] = None  # Can also use NVIDIA_API_KEY env var
    nvidia_base_url: str = "https://integrate.api.nvidia.com/v1"
    nvidia_model: str = "meta/llama-3.1-8b-instruct"


class AgentSettings(BaseModel):
    """Agent configuration"""
    default_agent: str = "assistant"
    max_steps: int = 20
    system_prompt: Optional[str] = None
    enabled_tools: List[str] = field(default_factory=lambda: ["file", "web", "code"])


class WebSettings(BaseModel):
    """Web server configuration"""
    host: str = "127.0.0.1"
    port: int = 8080
    enable_cors: bool = True
    ws_heartbeat: int = 30


class DesktopSettings(BaseModel):
    """Desktop app configuration"""
    width: int = 1200
    height: int = 800
    title: str = "Moon AI Agent"
    debug: bool = False


class TerminalSettings(BaseModel):
    """Terminal/TUI configuration"""
    theme: str = "dark"
    show_timestamps: bool = True
    max_history: int = 1000
    syntax_highlighting: bool = True


class MemorySettings(BaseModel):
    """Memory system configuration"""
    enabled: bool = True
    db_path: str = "memory.db"
    vector_store_path: str = "vector_store"
    max_short_term: int = 50
    max_long_term: int = 1000
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"


class SkillsSettings(BaseModel):
    """Skills system configuration"""
    enabled: bool = True
    skills_dir: str = "skills"
    auto_load: bool = True


class Settings(BaseSettings):
    """Main settings class with all subsections"""
    llm: LLMSettings = Field(default_factory=LLMSettings)
    agent: AgentSettings = Field(default_factory=AgentSettings)
    web: WebSettings = Field(default_factory=WebSettings)
    desktop: DesktopSettings = Field(default_factory=DesktopSettings)
    terminal: TerminalSettings = Field(default_factory=TerminalSettings)
    memory: MemorySettings = Field(default_factory=MemorySettings)
    skills: SkillsSettings = Field(default_factory=SkillsSettings)
    
    # Runtime
    data_dir: str = "data"
    logs_dir: str = "logs"
    
    class Config:
        env_nested_delimiter = "__"
        env_file = ".env"
        extra = "allow"


class SettingsManager:
    """Manages settings with file persistence and environment overrides"""
    
    def __init__(self, config_path: Optional[str] = None):
        self.config_path = config_path or "config.yaml"
        self._settings: Optional[Settings] = None
        self._load()
    
    def _load(self) -> None:
        """Load settings from YAML file with environment overrides"""
        data = {}
        
        # Load from YAML if exists
        if os.path.exists(self.config_path):
            with open(self.config_path, 'r') as f:
                data = yaml.safe_load(f) or {}
        
        # Create settings (pydantic handles env vars automatically)
        self._settings = Settings(**data)
    
    @property
    def settings(self) -> Settings:
        return self._settings
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a setting by dot-notation key (e.g., 'llm.model')"""
        keys = key.split('.')
        obj = self._settings
        for k in keys:
            if hasattr(obj, k):
                obj = getattr(obj, k)
            else:
                return default
        return obj
    
    def set(self, key: str, value: Any) -> None:
        """Set a setting by dot-notation key"""
        keys = key.split('.')
        obj = self._settings
        for k in keys[:-1]:
            obj = getattr(obj, k)
        setattr(obj, keys[-1], value)
    
    def save(self) -> None:
        """Save settings to YAML file"""
        data = self._settings.model_dump()
        with open(self.config_path, 'w') as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)
    
    def reset(self) -> None:
        """Reset to defaults"""
        self._settings = Settings()
    
    def ensure_dirs(self) -> None:
        """Ensure required directories exist"""
        for dir_name in [self._settings.data_dir, self._settings.logs_dir, 
                         self._settings.skills.skills_dir]:
            Path(dir_name).mkdir(parents=True, exist_ok=True)


# Global settings instance
_settings_manager: Optional[SettingsManager] = None


def get_settings(config_path: Optional[str] = None) -> SettingsManager:
    """Get or create the global settings manager"""
    global _settings_manager
    if _settings_manager is None or config_path:
        _settings_manager = SettingsManager(config_path)
    return _settings_manager


def load_settings(config_path: Optional[str] = None) -> Settings:
    """Load and return settings object"""
    return get_settings(config_path).settings