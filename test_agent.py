import asyncio
import logging
from typing import Optional

from utils import Config, init_logging, setup_logger, get_timezone
from llm import LLMRouter
from agents.base_agent import BaseAgent
from plugins.example_plugin.plugin import CalculatorPlugin
from plugins.scheduler_plugin.plugin import SchedulerPlugin

#init_logging(level=logging.INFO)
logger = setup_logger(__name__)

class ConsoleInterface:
    """Интерфейс для взаимодействия с агентом через консоль"""
    
    def __init__(self):
        self.agent: Optional[BaseAgent] = None
        
    async def setup(self):
        """Инициализация агента и плагинов"""
        # Загружаем конфигурацию
        config = Config.load()
        
        # Получаем часовой пояс системы
        timezone = get_timezone()
        logger.info("Using timezone: %s", str(timezone))
        
        # Инициализируем LLM через роутер
        router = LLMRouter()
        llm = router.create_instance(
            provider="ollama",
            api_key="",  # Не требуется для локального Ollama
            model="herenickname/t-tech_T-lite-it-1.0:q4_k_m"
        )

        #llm = router.create_instance(
        #    provider="deepseek",
        #    api_key=config.deepseek_api_key,
        #    model="deepseek-chat"
        #)

        # Создаем агента
        self.agent = BaseAgent(llm=llm, auto_load_plugins=False)
        
        # Создаем и инициализируем плагины
        calculator = CalculatorPlugin()
        scheduler = SchedulerPlugin(tick_interval=1.0, timezone=str(timezone))
        
        # Инициализируем плагины
        await calculator.setup()
        await scheduler.setup()
        
        # Регистрируем плагины
        self.agent.plugin_manager.register_plugin("calculator", calculator)
        self.agent.plugin_manager.register_plugin("scheduler", scheduler)
        
        # Показываем доступные инструменты
        print("\nДоступные инструменты:")
        for plugin in self.agent.plugin_manager.get_all_plugins():
            print(f"\n📦 Плагин: {plugin.name}")
            for tool in plugin.get_tools():
                print(f"  🔧 {tool.name}: {tool.description}")

        print(f"\n🌍 Используется часовой пояс: {timezone}")
        print("\n💡 Бот готов к работе! Для выхода введите 'exit'\n")
        
    async def cleanup(self):
        """Очистка ресурсов"""
        if self.agent:
            await self.agent.cleanup()
            
    async def process_input(self, user_input: str) -> bool:
        """
        Обработка пользовательского ввода
        
        Returns:
            bool: True если нужно продолжить диалог, False для выхода
        """
        if user_input.lower() == 'exit':
            print("\n👋 До свидания!")
            return False
            
        try:
            # Обрабатываем сообщение с системным промптом
            response = await self.agent.process_message(
                message=user_input,
                system_prompt=(
                    "Ты - полезный ассистент. Отвечай кратко и по делу. "
                    "ВАЖНО: Для ЛЮБЫХ математических вычислений ты ДОЛЖЕН использовать инструмент calculate. "
                    "НИКОГДА не пытайся вычислять самостоятельно, даже если кажется, что это просто. "
                    "Для планирования задач используй инструменты планировщика. "
                    "При планировании учитывай часовой пояс пользователя"
                ),
            )
            print(f"\n🤖 {response}\n")
            
        except Exception as e:
            print(f"\n❌ Произошла ошибка: {str(e)}\n")
            logger.exception("Error processing message")
            
        return True


async def main():
    # Создаем интерфейс
    interface = ConsoleInterface()
    
    try:
        # Инициализируем интерфейс
        await interface.setup()
        
        # Основной цикл
        while True:
            user_input = input("👤 ").strip()
            if not await interface.process_input(user_input):
                break
                
    finally:
        # Очищаем ресурсы
        await interface.cleanup()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n\n👋 Работа прервана пользователем")
    except Exception as e:
        logger.exception("Unexpected error occurred") 