import os
import sys
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime

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
LLM_PROVIDER = "deepseek"
LLM_MODEL = "deepseek-chat"
LLM_API_KEY = config.deepseek_api_key

# Системный промпт для агента
SYSTEM_PROMPT = """
Ты - полезный ассистент. Отвечай кратко и по делу. 
ВАЖНО: Для ЛЮБЫХ математических вычислений ты ДОЛЖЕН использовать инструмент calculate. 
НИКОГДА не пытайся вычислять самостоятельно, даже если кажется, что это просто. 
Для планирования задач используй инструменты планировщика. 
При планировании учитывай часовой пояс пользователя
""".strip()

#init_logging(level=logging.INFO)
logger = setup_logger(__name__)


async def handle_message(message: IOMessage, agent: BaseAgent, telegram: TelegramPlugin):
    """Обработка входящего сообщения из Telegram"""
    logger.info(f"Processing message: {message.type} from user {message.metadata.get('user_id')}")
    
    if message.type == "telegram_message":
        # Отправляем typing... пока готовим ответ
        await telegram.output_hook(
            IOMessage(
                type="action",
                content="typing",
                metadata={"chat_id": message.metadata["chat_id"]}
            )
        )
        
        try:
            # Обрабатываем сообщение через агента
            response = await agent.process_message(
                message=message.content,
                system_prompt=SYSTEM_PROMPT
            )
            
            # Отправляем ответ
            await telegram.output_hook(
                IOMessage(
                    type="message",
                    content=response,
                    metadata={"chat_id": message.metadata["chat_id"]}
                )
            )
        except Exception as e:
            logger.error(f"Error processing message: {e}")
            await telegram.output_hook(
                IOMessage(
                    type="message",
                    content="Извините, произошла ошибка при обработке сообщения. Попробуйте позже.",
                    metadata={"chat_id": message.metadata["chat_id"]}
                )
            )


async def setup_agent(llm) -> BaseAgent:
    """Создание и настройка агента"""
    if not config.telegram_token:
        raise ValueError("Telegram token not provided in config")
        
    # Создаем базового агента
    agent = BaseAgent(llm=llm)
    
    # Создаем и регистрируем плагины
    telegram = TelegramPlugin()
    scheduler = SchedulerPlugin(
        tick_interval=1.0,
        timezone=str(get_timezone())
    )
    calculator = CalculatorPlugin()
    
    # Инициализируем плагины
    await telegram.setup(token=config.telegram_token)
    await scheduler.setup()
    await calculator.setup()
    
    # Регистрируем плагины
    agent.plugin_manager.register_plugin("telegram", telegram)
    agent.plugin_manager.register_plugin("scheduler", scheduler)
    agent.plugin_manager.register_plugin("calculator", calculator)
    
    # Устанавливаем обработчик
    telegram.message_handler = lambda msg: handle_message(msg, agent, telegram)
    telegram.handlers.message_handler = lambda msg: handle_message(msg, agent, telegram)
    
    # Отправляем приветственное сообщение
    user_id = "test_user"
    chat_id = await telegram.check_chat_link(user_id)
    
    if chat_id:
        print(f"\n✅ Уже есть привязка к чату: {chat_id}")
        await telegram.output_hook(
            IOMessage(
                type="message",
                content="Привет! Я готов к работе. Отправь мне сообщение, и я постараюсь помочь.",
                metadata={"chat_id": chat_id}
            )
        )
    else:
        key = await telegram.generate_key(user_id)
        print(f"\n🔑 Ключ для привязки: {key}")
        print(f"🔗 Используйте команду: /start {key}")
    
    print("\n👋 Бот запущен. Для остановки нажмите Ctrl+C")
    
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