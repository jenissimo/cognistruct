import os
import asyncio
import logging
import signal
from typing import Optional, Dict, Any
from datetime import datetime
from functools import partial

from cognistruct.utils import Config, init_logging, setup_logger, get_timezone
from cognistruct.llm import LLMRouter
from cognistruct.core import BaseAgent
from cognistruct.plugins.io.telegram import TelegramPlugin
from cognistruct.plugins.tools.scheduler import SchedulerPlugin
from cognistruct.plugins.tools.calculate import CalculatorPlugin
from cognistruct.plugins.tools.internet import InternetPlugin

# Загружаем конфигурацию
config = Config.load()

# Конфигурация LLM
LLM_CONFIG = {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "api_key": config.deepseek_api_key,
    #"provider": "ollama",
    #"model": "llama3.1",
    #"api_key": "ollama",
    "provider": "proxyapi",
    "model": "gpt-4o",
    "api_key": Config.load().proxyapi_key,
    "max_tokens": 8192,

    "temperature": 0.7  # Добавляем температуру (0.0 - более точные ответы, 1.0 - более креативные)
}

# Системный промпт для агента
SYSTEM_PROMPT = """
Ты - полезный ассистент идеально владеющий русским языком. Отвечай на русском языке. 

Ты можешь использовать инструменты для поиска информации в интернете.

Не используй повторно один и тот же инструмент дважды.
Используй инструменты только когда это действительно нужно.
""".strip()

init_logging(level=logging.DEBUG)
logger = setup_logger(__name__)

async def main():
    """Точка входа"""
    try:
        # Проверяем наличие токена
        if not config.telegram_token:
            raise ValueError("Telegram token not provided in config")
            
        # Инициализируем LLM
        llm = LLMRouter().create_instance(**LLM_CONFIG)
        
        # Создаем агента, плагины инициализируются вручную
        agent = BaseAgent(llm=llm, auto_load_plugins=False)
        
        # Создаем минимальный набор плагинов
        telegram = TelegramPlugin(telegram_user_id="test_user")
        scheduler = SchedulerPlugin(
            tick_interval=1.0,
            timezone=str(get_timezone())
        )
        calculator = CalculatorPlugin()
        internet = InternetPlugin(
            max_search_results=5,  # Максимум результатов поиска
            min_word_count=20      # Минимум слов в блоке текста
        )
        
        # Инициализируем плагины
        telegram_status = await telegram.setup(token=config.telegram_token)
        await scheduler.setup()
        await calculator.setup()
        await internet.setup()
        
        # Регистрируем плагины
        agent.plugin_manager.register_plugin("telegram", telegram)
        agent.plugin_manager.register_plugin("scheduler", scheduler)
        agent.plugin_manager.register_plugin("calculator", calculator)
        agent.plugin_manager.register_plugin("internet", internet)
        
        # Подключаем обработчик к телеграму с предустановленными параметрами
        telegram.set_message_handler(
            partial(
                agent.handle_message,
                system_prompt=SYSTEM_PROMPT,
                stream=True  # Включаем стриминг
            )
        )
        
        # Запускаем агента
        await agent.start()
        
        print("\n👋 Бот запущен. Для остановки нажмите Ctrl+C")

        # Выводим статус инициализации
        if telegram_status["chat_status"] == "linked":
            print(f"\n✅ Привязанный чат: {telegram_status['chat_id']}")
            await telegram.send_welcome_message(telegram_status['chat_id'])
        else:
            print("\n🔑 Необходимо привязать чат")
            print(f"\n🔑 Ключ для привязки: {telegram_status['key']}")
            print(f"🔗 Используйте команду: /start {telegram_status['key']}")

        # Создаем future для обработки сигнала завершения
        stop_event = asyncio.Event()
        
        def handle_interrupt():
            print("\n\n👋 Получен сигнал завершения, останавливаем бота...")
            stop_event.set()
            
        # Устанавливаем обработчик SIGINT (Ctrl+C)
        loop = asyncio.get_running_loop()
        loop.add_signal_handler(signal.SIGINT, handle_interrupt)
        
        # Ждем сигнала завершения
        await stop_event.wait()
            
    except Exception as e:
        logger.exception("Unexpected error occurred")
        raise
    finally:
        print("\n🛑 Останавливаем бота...")
        if 'agent' in locals():
            await agent.cleanup()
        print("✅ Бот остановлен")


if __name__ == "__main__":
    asyncio.run(main()) 