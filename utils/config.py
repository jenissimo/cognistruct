import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from .logging import setup_logger


logger = setup_logger(__name__)


class Config(BaseModel):
    """Конфигурация приложения"""
    deepseek_api_key: str
    telegram_token: Optional[str] = None
    plugins_dir: str = "plugins"
    db_url: str = "sqlite+aiosqlite:///plugins.db"

    @classmethod
    def load(cls) -> "Config":
        """Загружает конфигурацию из переменных окружения"""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        
        # Пробуем загрузить из файла
        config_file = Path.home() / ".cognistruct" / "config"
        if config_file.exists():
            lines = config_file.read_text().strip().splitlines()
            if len(lines) >= 1:
                api_key = api_key or lines[0].strip()
                logger.debug("Loaded API key from config file")
            if len(lines) >= 2:
                telegram_token = telegram_token or lines[1].strip()
                logger.debug("Loaded Telegram token from config file")
                
        if not api_key:
            logger.error("DeepSeek API key not found")
            raise ValueError(
                "DeepSeek API key not found. Please set DEEPSEEK_API_KEY "
                "environment variable or create ~/.cognistruct/config file"
            )
            
        return cls(
            deepseek_api_key=api_key,
            telegram_token=telegram_token
        )

    def save(self):
        """Сохраняет конфигурацию в файл"""
        config_dir = Path.home() / ".cognistruct"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config_file = config_dir / "config"
        with config_file.open("w") as f:
            f.write(self.deepseek_api_key + "\n")
            if self.telegram_token:
                f.write(self.telegram_token + "\n")
                
        logger.info("Saved configuration to %s", config_file) 