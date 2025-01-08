import os
import sys
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime
from functools import partial

# Добавляем родительскую директорию в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import Config, init_logging, setup_logger, get_timezone
from llm import LLMRouter
from agents.base_agent import BaseAgent
from plugins.base_plugin import IOMessage
from plugins.telegram_plugin.plugin import TelegramPlugin
from plugins.scheduler_plugin.plugin import SchedulerPlugin
from plugins.example_plugin.plugin import CalculatorPlugin

# Загружаем конфигурацию
config = Config.load()

# Конфигурация LLM
LLM_CONFIG = {
    "provider": "deepseek",
    "model": "deepseek-chat",
    "api_key": config.deepseek_api_key
}

# Системный промпт для агента
SYSTEM_PROMPT = """
Ты - полезный ассистент. Отвечай кратко и по делу. 
ВАЖНО: Для ЛЮБЫХ математических вычислений ты ДОЛЖЕН использовать инструмент calculate. 
НИКОГДА не пытайся вычислять самостоятельно, даже если кажется, что это просто. 
Для планирования задач используй инструменты планировщика. 
При планировании учитывай часовой пояс пользователя.
""".strip()

#init_logging(level=logging.DEBUG)
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
        telegram = TelegramPlugin(user_id="test_user")
        scheduler = SchedulerPlugin(
            tick_interval=1.0,
            timezone=str(get_timezone())
        )
        calculator = CalculatorPlugin()
        
        # Инициализируем плагины
        telegram_status = await telegram.setup(token=config.telegram_token)
        await scheduler.setup()
        await calculator.setup()
        
        # Регистрируем плагины
        agent.plugin_manager.register_plugin("telegram", telegram)
        agent.plugin_manager.register_plugin("scheduler", scheduler)
        agent.plugin_manager.register_plugin("calculator", calculator)
        
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
        import signal
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