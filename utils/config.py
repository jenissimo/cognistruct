import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from .logging import setup_logger


logger = setup_logger(__name__)


class Config(BaseModel):
    """Конфигурация приложения"""
    deepseek_api_key: str
    plugins_dir: str = "plugins"
    db_url: str = "sqlite+aiosqlite:///plugins.db"

    @classmethod
    def load(cls) -> "Config":
        """Загружает конфигурацию из переменных окружения"""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        if not api_key:
            # Пробуем загрузить из файла
            config_file = Path.home() / ".cognistruct" / "config"
            if config_file.exists():
                api_key = config_file.read_text().strip()
                logger.debug("Loaded API key from config file")
                
        if not api_key:
            logger.error("DeepSeek API key not found")
            raise ValueError(
                "DeepSeek API key not found. Please set DEEPSEEK_API_KEY "
                "environment variable or create ~/.cognistruct/config file"
            )
            
        return cls(deepseek_api_key=api_key)

    def save(self):
        """Сохраняет конфигурацию в файл"""
        config_dir = Path.home() / ".cognistruct"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config_file = config_dir / "config"
        config_file.write_text(self.deepseek_api_key)
        logger.info("Saved configuration to %s", config_file) 