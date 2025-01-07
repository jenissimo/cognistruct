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

# Загружаем конфигурацию
config = Config.load()

# Конфигурация LLM
LLM_PROVIDER = "ollama"
LLM_MODEL = "herenickname/t-tech_T-lite-it-1.0:q4_k_m"
LLM_API_KEY = ""  # Не требуется для локального Ollama

# Системный промпт для агента
SYSTEM_PROMPT = """
Ты - полезный ассистент. Отвечай кратко и по делу. 
ВАЖНО: Для ЛЮБЫХ математических вычислений ты ДОЛЖЕН использовать инструмент calculate. 
НИКОГДА не пытайся вычислять самостоятельно, даже если кажется, что это просто. 
Для планирования задач используй инструменты планировщика. 
При планировании учитывай часовой пояс пользователя
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
        # Обрабатываем сообщение через агента
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
    
    # Инициализируем плагины
    await calculator.setup()
    await scheduler.setup()
    
    # Регистрируем плагины
    agent.plugin_manager.register_plugin("calculator", calculator)
    agent.plugin_manager.register_plugin("scheduler", scheduler)
    
    # Показываем доступные инструменты
    print("\nДоступные инструменты:")
    for plugin in agent.plugin_manager.get_all_plugins():
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
            user_input = input("👤 ").strip()
            if not await handle_console_input(user_input, agent):
                break
                
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