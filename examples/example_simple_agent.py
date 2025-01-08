import os
import sys
import asyncio
import logging
from typing import Optional

# Добавляем родительскую директорию в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import Config, init_logging, setup_logger, get_timezone
from llm import LLMRouter
from agents.base_agent import BaseAgent
from plugins.example_plugin.plugin import CalculatorPlugin
from plugins.scheduler_plugin.plugin import SchedulerPlugin
from plugins.short_term_memory.plugin import ShortTermMemoryPlugin
from plugins.console_plugin.plugin import ConsolePlugin, IOMessage

# Загружаем конфигурацию
config = Config.load()

# Конфигурация LLM
LLM_PROVIDER = "deepseek"
LLM_MODEL = "deepseek-chat"
LLM_API_KEY = config.deepseek_api_key

LLM_PROVIDER = "ollama"
LLM_MODEL = "qwen2.5"
LLM_API_KEY = "ollama"

# Системный промпт для агента
SYSTEM_PROMPT = """
Ты - полезный ассистент с краткосрочной памятью. Используй контекст из предыдущих сообщений, чтобы давать более релевантные ответы.

ВАЖНО:
1. Для ЛЮБЫХ математических вычислений используй инструмент calculate
2. НИКОГДА не пытайся вычислять самостоятельно
3. Если в контексте есть предыдущие сообщения (recent_messages), используй их для поддержания связности диалога

Пример использования контекста:
User: Какой язык программирования мы обсуждали?
Assistant: Судя по нашей предыдущей беседе, мы обсуждали Python в контексте асинхронного программирования.
""".strip()

#init_logging(level=logging.DEBUG)
logger = setup_logger(__name__)


async def handle_console_input(user_input: str, agent: BaseAgent) -> bool:
    """
    Обработка пользовательского ввода из консоли
    
    Returns:
        bool: True если нужно продолжить диалог, False для выхода
    """
    if user_input.lower() == 'exit':
        print("\n👋 До свидания!")
        return False
        
    try:
        # Создаем объект сообщения
        message = IOMessage(
            type="text",
            content=user_input,
            source="console"
        )
        
        # Получаем консольный плагин и передаем сообщение
        console = agent.plugin_manager.get_plugin("console")
        if console and console.message_handler:
            await console.message_handler(message)
        
    except Exception as e:
        print(f"\n❌ Произошла ошибка: {str(e)}\n")
        logger.exception("Error processing message")
        
    return True


async def setup_agent(llm) -> BaseAgent:
    """Создание и настройка агента"""
    # Создаем базового агента
    agent = BaseAgent(llm=llm, auto_load_plugins=False)
    
    # Создаем и регистрируем плагины
    calculator = CalculatorPlugin()
    scheduler = SchedulerPlugin(
        tick_interval=1.0,
        timezone=str(get_timezone())
    )
    short_term_memory = ShortTermMemoryPlugin(
        max_messages=15
    )
    console = ConsolePlugin(
        prompt="👤 ",
        exit_command="exit",
        exit_message="\n👋 До свидания!",
        use_markdown=True,
        use_emojis=True,
        refresh_rate=10  # Частота обновления стриминга
    )
    
    # Устанавливаем обработчик сообщений для консоли
    async def handle_message(message: IOMessage):
        try:
            # Обрабатываем сообщение через агента
            response = await agent.process_message(
                message=message.content,
                system_prompt=SYSTEM_PROMPT,
                #stream=True  # Включаем стриминг
            )
            
            # Для не-стрим ответов ничего не делаем, так как base_agent уже вызвал output_hook
            if not hasattr(response, '__aiter__'):
                return
            
            # Для стрим-ответов обрабатываем через output_hook
            await console.output_hook(IOMessage(
                content=response,
                type="stream",
                source="agent",
                stream=response
            ))
            
        except Exception as e:
            logger.exception("Error processing message")
            await console.output_hook(IOMessage(
                content=f"Произошла ошибка: {str(e)}",
                type="error",
                source="agent"
            ))
    
    console.set_message_handler(handle_message)
    
    # Инициализируем плагины
    await calculator.setup()
    await scheduler.setup()
    await short_term_memory.setup()
    await console.setup()
    
    # Регистрируем плагины
    agent.plugin_manager.register_plugin("short_term_memory", short_term_memory)
    agent.plugin_manager.register_plugin("calculator", calculator)
    agent.plugin_manager.register_plugin("scheduler", scheduler)
    agent.plugin_manager.register_plugin("console", console)
    
    # Показываем доступные инструменты
    print("\nДоступные инструменты:")
    for plugin in [calculator, scheduler]:
        print(f"\n📦 Плагин: {plugin.name}")
        for tool in plugin.get_tools():
            print(f"  🔧 {tool.name}: {tool.description}")

    print(f"\n🌍 Используется часовой пояс: {get_timezone()}")
    print("\n💡 Бот готов к работе! Для выхода введите 'exit'\n")
    
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
        
        # Получаем консольный плагин и запускаем обработку ввода
        console = agent.plugin_manager.get_plugin("console")
        await console.start()
        
    except Exception as e:
        logger.exception("Unexpected error occurred")
        raise
    finally:
        if 'agent' in locals():
            await agent.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\033[2K\033[G", end="")  # Очищаем текущую строку
        print("\n👋 Работа прервана пользователем") 