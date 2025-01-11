import os
import sys
import asyncio
import logging
from typing import Optional

# Добавляем родительскую директорию в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import Config, init_logging, setup_logger
from llm import LLMRouter
from core import BaseAgent
from plugins.rest_api.plugin import RESTApiPlugin
from plugins.versioned_storage.plugin import VersionedStoragePlugin

# Загружаем конфигурацию
config = Config.load()

# Конфигурация LLM
LLM_PROVIDER = "deepseek"
LLM_MODEL = "deepseek-chat"
LLM_API_KEY = config.deepseek_api_key

# Системный промпт для агента
SYSTEM_PROMPT = """
Ты - полезный ассистент с доступом через REST API.
Используй доступные инструменты для помощи пользователю.
""".strip()

init_logging(level=logging.INFO)
logger = setup_logger(__name__)


async def setup_agent(llm) -> BaseAgent:
    """Создание и настройка агента"""
    # Создаем агента
    agent = BaseAgent(llm=llm)
    
    # Создаем и регистрируем плагины
    storage = VersionedStoragePlugin()
    rest_api = RESTApiPlugin(
        port=8000,
        enable_auth=False,
        allowed_origins=["http://localhost:3000"]  # Для фронтенда
    )
    
    # Инициализируем плагины
    await storage.setup()
    await rest_api.setup()
    
    # Регистрируем плагины
    agent.plugin_manager.register_plugin("storage", storage)
    agent.plugin_manager.register_plugin("rest_api", rest_api)
    
    logger.info(f"\n🚀 REST API запущен на http://localhost:8000")
    logger.info(f"📚 Swagger документация: http://localhost:8000/docs")
    logger.info(f"📖 ReDoc документация: http://localhost:8000/redoc")
    logger.warning("⚠️ Авторизация отключена! Рекомендуется настроить через setup_config.py")
    
    return agent


async def main():
    """Точка входа"""
    try:
        # Инициализируем LLM
        router = LLMRouter()
        llm = router.create_instance(
            provider=LLM_PROVIDER,
            api_key=LLM_API_KEY,
            model=LLM_MODEL
        )
        
        # Создаем и настраиваем агента
        agent = await setup_agent(llm)
        
        # Запускаем агента
        await agent.start()
        
        # Ждем сигнала завершения
        try:
            while True:
                await asyncio.sleep(1)
        except asyncio.CancelledError:
            pass
            
    except KeyboardInterrupt:
        print("\n\n👋 Работа прервана пользователем")
    except Exception as e:
        logger.exception("Unexpected error occurred")
        raise
    finally:
        if 'agent' in locals():
            await agent.cleanup()


if __name__ == "__main__":
    asyncio.run(main()) 