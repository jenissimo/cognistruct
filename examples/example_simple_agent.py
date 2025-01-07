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

# Загружаем конфигурацию
config = Config.load()

# Конфигурация LLM
LLM_PROVIDER = "deepseek"
LLM_MODEL = "deepseek-chat"
LLM_API_KEY = config.deepseek_api_key

# Системный промпт для агента
SYSTEM_PROMPT = """
Ты - полезный ассистент с краткосрочной памятью. Используй контекст из предыдущих сообщений, чтобы давать более релевантные ответы.

ВАЖНО:
1. Для ЛЮБЫХ математических вычислений используй инструмент calculate
2. НИКОГДА не пытайся вычислять самостоятельно
3. Для планирования задач используй инструменты планировщика
4. При планировании учитывай часовой пояс пользователя
5. Если в контексте есть предыдущие сообщения (recent_messages), используй их для поддержания связности диалога

Пример использования контекста:
User: Какой язык программирования мы обсуждали?
Assistant: Судя по нашей предыдущей беседе, мы обсуждали Python в контексте асинхронного программирования.
""".strip()

init_logging(level=logging.INFO)
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
        # Обрабатываем сообщение через агента с учетом контекста
        response = await agent.process_message(
            message=user_input,
            system_prompt=SYSTEM_PROMPT
        )
        print(f"\n🤖 {response}\n")
        
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
    
    # Создаем плагин памяти с хранением последних 15 сообщений
    # Это даст нам контекст примерно из 7-8 обменов репликами,
    # что достаточно для поддержания связного диалога
    short_term_memory = ShortTermMemoryPlugin(
        max_messages=15  # Храним больше сообщений для лучшего контекста
    )
    
    # Инициализируем плагины
    await calculator.setup()
    await scheduler.setup()
    await short_term_memory.setup()
    
    # Регистрируем плагины в порядке приоритета
    # Memory первым, чтобы контекст добавлялся до обработки другими плагинами
    agent.plugin_manager.register_plugin("short_term_memory", short_term_memory)
    agent.plugin_manager.register_plugin("calculator", calculator)
    agent.plugin_manager.register_plugin("scheduler", scheduler)
    
    # Показываем доступные инструменты (только для калькулятора и планировщика)
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
        
        # Основной цикл обработки ввода
        while True:
            try:
                user_input = input("👤 ").strip()
                if not await handle_console_input(user_input, agent):
                    break
            except KeyboardInterrupt:
                # Очищаем буфер ввода и печатаем новую строку
                print("\n👋 Работа прервана пользователем")
                break
                
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
        # Очищаем буфер ввода и печатаем новую строку
        print("\n👋 Работа прервана пользователем") 