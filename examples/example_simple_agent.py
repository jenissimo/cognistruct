import os
import sys
import asyncio
import logging
from functools import partial

# Добавляем родительскую директорию в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import Config
from llm import LLMRouter
from core import BaseAgent
from plugins.example_plugin import CalculatorPlugin
from plugins.console_plugin import ConsolePlugin

# Раскомментируйте для включения логирования
#from utils.logging import init_logging
#init_logging(level=logging.DEBUG)

# Конфигурация LLM (выберите один вариант)
LLM_CONFIG = {
    # Для Ollama (локальный):
    #"provider": "ollama",
    #"model": "qwen2.5",
    #"api_key": "ollama",
    
    # Для DeepSeek:
     "provider": "deepseek",
     "model": "deepseek-chat",
     "api_key": Config.load().deepseek_api_key,
     "temperature": 0.5  # Добавляем температуру (0.0 - более точные ответы, 1.0 - более креативные)
}

# Системный промпт для агента
SYSTEM_PROMPT = """
Ты - полезный ассистент. Для математических вычислений используй инструмент calculate.
Используй инструменты ТОЛЬКО когда это действительно необходимо:
- calculate: ТОЛЬКО для математических вычислений
- search: ТОЛЬКО когда нужно найти актуальную информацию
- crawl: ТОЛЬКО когда нужно получить содержимое конкретной веб-страницы

НЕ используй инструменты для:
- Простых ответов на вопросы
- Общих рассуждений
- Базовых математических операций, которые можно выполнить в уме
""".strip()

async def main():
    """Точка входа"""
    try:
        # Инициализируем LLM
        llm = LLMRouter().create_instance(**LLM_CONFIG)
        
        # Создаем агента, плагины инициализируются вручную
        agent = BaseAgent(llm=llm, auto_load_plugins=False)
        
        # Создаем минимальный набор плагинов
        calculator = CalculatorPlugin()
        console = ConsolePlugin(
            prompt="👤 ",
            exit_command="exit",
            exit_message="\n👋 До свидания!",
            use_markdown=True,
            use_emojis=True,
            refresh_rate=10  # Частота обновления стриминга
        )

        print("👋 Добро пожаловать в наш пример!")
        print(f"👉 LLM: {LLM_CONFIG['model']}")
        print("👉 Введите ваш запрос к агенту:")
        print("👉 Введите exit для выхода.")
        
        # Подключаем обработчик к консоли с предустановленными параметрами
        console.set_message_handler(
            partial(
                agent.handle_message,
                system_prompt=SYSTEM_PROMPT,
                stream=True  # Включаем стриминг обратно
            )
        )
        
        # Инициализируем плагины
        await calculator.setup()
        await console.setup()
        
        # Регистрируем плагины
        agent.plugin_manager.register_plugin("calculator", calculator)
        agent.plugin_manager.register_plugin("console", console)
        
        # Запускаем агента и консоль
        await agent.start()
        await console.start()
        
    except Exception as e:
        print(f"\n❌ Неожиданная ошибка: {str(e)}")
        raise
    finally:
        if 'agent' in locals():
            await agent.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Работа прервана пользователем") 