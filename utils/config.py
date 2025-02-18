import os
from pathlib import Path
from typing import Optional

from pydantic import BaseModel
from .logging import setup_logger


logger = setup_logger(__name__)


class Config(BaseModel):
    """Конфигурация приложения"""
    deepseek_api_key: str
    proxyapi_key: Optional[str] = None
    telegram_token: Optional[str] = None
    admin_username: Optional[str] = None
    admin_password: Optional[str] = None
    plugins_dir: str = "plugins"
    db_url: str = "sqlite+aiosqlite:///plugins.db"

    @classmethod
    def load(cls) -> "Config":
        """Загружает конфигурацию из переменных окружения"""
        api_key = os.getenv("DEEPSEEK_API_KEY")
        proxy_key = os.getenv("PROXYAPI_KEY")
        telegram_token = os.getenv("TELEGRAM_BOT_TOKEN")
        admin_username = os.getenv("ADMIN_USERNAME")
        admin_password = os.getenv("ADMIN_PASSWORD")
        
        # Пробуем загрузить из файла
        config_file = Path.home() / ".cognistruct" / "config"
        if config_file.exists():
            lines = config_file.read_text().strip().splitlines()
            if len(lines) >= 1:
                api_key = api_key or lines[0].strip()
                logger.debug("Loaded API key from config file")
            if len(lines) >= 2:
                proxy_key = proxy_key or lines[1].strip()
                logger.debug("Loaded ProxyAPI key from config file")
            if len(lines) >= 3:
                telegram_token = telegram_token or lines[2].strip()
                logger.debug("Loaded Telegram token from config file")
            if len(lines) >= 4:
                admin_username = admin_username or lines[3].strip()
                logger.debug("Loaded admin username from config file")
            if len(lines) >= 5:
                admin_password = admin_password or lines[4].strip()
                logger.debug("Loaded admin password from config file")
                
        if not api_key:
            logger.error("DeepSeek API key not found")
            raise ValueError(
                "DeepSeek API key not found. Please set DEEPSEEK_API_KEY "
                "environment variable or create ~/.cognistruct/config file"
            )
            
        return cls(
            deepseek_api_key=api_key,
            proxyapi_key=proxy_key,
            telegram_token=telegram_token,
            admin_username=admin_username,
            admin_password=admin_password
        )

    def save(self):
        """Сохраняет конфигурацию в файл"""
        config_dir = Path.home() / ".cognistruct"
        config_dir.mkdir(parents=True, exist_ok=True)
        
        config_file = config_dir / "config"
        with config_file.open("w") as f:
            f.write(self.deepseek_api_key + "\n")
            if self.proxyapi_key:
                f.write(self.proxyapi_key + "\n")
            else:
                f.write("\n")  # Пустая строка для сохранения порядка
            if self.telegram_token:
                f.write(self.telegram_token + "\n")
            else:
                f.write("\n")
            if self.admin_username:
                f.write(self.admin_username + "\n")
            else:
                f.write("\n")
            if self.admin_password:
                f.write(self.admin_password + "\n")
            else:
                f.write("\n")
                
        logger.info("Saved configuration to %s", config_file) 