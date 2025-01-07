import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime

from utils import Config, init_logging, setup_logger, get_timezone
from llm import LLMRouter
from plugins.base_plugin import IOMessage
from plugins.telegram_plugin.plugin import TelegramPlugin
from plugins.scheduler_plugin.plugin import SchedulerPlugin
from plugins.example_plugin.plugin import CalculatorPlugin
from plugins.plugin_manager import PluginManager

init_logging(level=logging.INFO)
logger = setup_logger(__name__)


async def handle_telegram_message(message: IOMessage, llm, plugin_manager, telegram):
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
            # Обрабатываем сообщение через LLM
            response = await llm.chat(
                messages=[{
                    "role": "system",
                    "content": (
                        "Ты - полезный ассистент. Отвечай кратко и по делу. "
                        "ВАЖНО: Для ЛЮБЫХ математических вычислений ты ДОЛЖЕН использовать инструмент calculate. "
                        "НИКОГДА не пытайся вычислять самостоятельно, даже если кажется, что это просто. "
                        "Для планирования задач используй инструменты планировщика. "
                        "При планировании учитывай часовой пояс пользователя"
                    )
                }, {
                    "role": "user",
                    "content": message.content
                }],
                tools=plugin_manager.get_tools()
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


async def setup_plugins(config: Config):
    """Инициализация и настройка плагинов"""
    if not config.telegram_token:
        raise ValueError("Telegram token not provided in config")
        
    # Создаем плагины
    plugins = {
        "telegram": TelegramPlugin(),
        "scheduler": SchedulerPlugin(
            tick_interval=1.0,
            timezone=str(get_timezone())
        ),
        "calculator": CalculatorPlugin()
    }
    
    # Инициализируем плагины
    await plugins["telegram"].setup(token=config.telegram_token)
    await plugins["scheduler"].setup()
    await plugins["calculator"].setup()
    
    # Создаем менеджер плагинов
    plugin_manager = PluginManager()
    
    # Регистрируем плагины
    for name, plugin in plugins.items():
        plugin_manager.register_plugin(name, plugin)
        
    return plugins, plugin_manager


async def run_bot(llm, plugins: Dict[str, Any], plugin_manager: PluginManager):
    """Запуск бота"""
    telegram = plugins["telegram"]
    
    # Настраиваем обработчик сообщений
    telegram.message_handler = lambda msg: handle_telegram_message(msg, llm, plugin_manager, telegram)
    telegram.handlers.message_handler = lambda msg: handle_telegram_message(msg, llm, plugin_manager, telegram)
    
    # Проверяем существующую привязку
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
    
    # Запускаем поллинг
    await telegram.start_polling()
    
    try:
        while True:
            await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass


async def cleanup_plugins(plugins: Dict[str, Any]):
    """Очистка ресурсов плагинов"""
    for plugin in plugins.values():
        await plugin.cleanup()


async def main():
    """Точка входа"""
    try:
        # Загружаем конфигурацию
        config = Config.load()
        
        # Инициализируем LLM
        router = LLMRouter()
        llm = router.create_instance(
            provider="deepseek",
            api_key=config.deepseek_api_key,
            model="deepseek-chat"
        )
        
        # Настраиваем плагины
        plugins, plugin_manager = await setup_plugins(config)
        
        # Запускаем бота
        await run_bot(llm, plugins, plugin_manager)
            
    except KeyboardInterrupt:
        print("\n\n👋 Работа прервана пользователем")
    except Exception as e:
        logger.exception("Unexpected error occurred")
        raise
    finally:
        if 'plugins' in locals():
            await cleanup_plugins(plugins)


if __name__ == "__main__":
    asyncio.run(main()) 