import os
import sys
import asyncio
import logging
from typing import Optional, Dict, Any
from datetime import datetime, timedelta

# Добавляем родительскую директорию в PYTHONPATH
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils import Config, init_logging, setup_logger, get_timezone
from llm import LLMRouter
from agents.base_agent import BaseAgent
from plugins.base_plugin import IOMessage
from plugins.telegram_plugin.plugin import TelegramPlugin
from plugins.scheduler_plugin.plugin import SchedulerPlugin
from plugins.versioned_storage.plugin import VersionedStoragePlugin
from plugins.internet_plugin.plugin import InternetPlugin

# Загружаем конфигурацию
config = Config.load()

# Конфигурация LLM
LLM_PROVIDER = "deepseek"
LLM_MODEL = "deepseek-chat"
LLM_API_KEY = config.deepseek_api_key

# Системные промпты
INTERVIEW_PROMPT = """
Ты - дружелюбный ассистент, проводящий интервью для настройки персонализированного дайджеста.
Твоя задача - узнать у пользователя:
1. Интересующие темы и области (технологии, наука, бизнес и т.д.)
2. Предпочитаемые источники информации
3. Частота получения дайджестов (раз в день/неделю)
4. Предпочитаемый формат (краткий/подробный)
5. Лучшее время для получения дайджеста

Веди диалог естественно, задавай уточняющие вопросы.
Когда соберешь всю информацию, используй инструмент save_preferences.
""".strip()

DIGEST_PROMPT = """
Ты - ассистент, который анализирует статьи и формирует персонализированные дайджесты.

При анализе статей:
1. Используй сохраненные предпочтения пользователя
2. Оценивай релевантность контента
3. Создавай краткие, но информативные резюме

При формировании дайджеста:
1. Группируй статьи по темам
2. Добавляй ссылки на оригиналы
3. Форматируй текст в Markdown
""".strip()

init_logging(level=logging.INFO)
logger = setup_logger(__name__)


class DigestAgent(BaseAgent):
    """Агент для создания персонализированных дайджестов"""
    
    def __init__(self, llm):
        super().__init__(llm=llm)
        self.interview_completed = False
        self.current_question = 0
        self.interview_data = {}
        
    async def save_preferences(self, chat_id: str) -> str:
        """Сохраняет предпочтения пользователя"""
        storage = self.plugin_manager.get_plugin("storage")
        
        # Генерируем ID для предпочтений
        prefs_id = storage.generate_id("preferences", f"user_{chat_id}")
        
        # Сохраняем предпочтения
        await storage.create({
            "key": prefs_id,
            "value": self.interview_data,
            "metadata": {
                "type": "user_preferences",
                "user_id": chat_id,
                "created_at": datetime.now().isoformat()
            }
        })
        
        return prefs_id
        
    async def setup_digest_schedule(self, chat_id: str, time: str, interval: str):
        """Настраивает расписание дайджестов"""
        scheduler = self.plugin_manager.get_plugin("scheduler")
        
        # Настраиваем регулярную проверку новых статей
        await scheduler.schedule_task(
            "crawl_articles",
            "0 */4 * * *",  # Каждые 4 часа
            {
                "chat_id": chat_id,
                "action": "crawl"
            }
        )
        
        # Настраиваем отправку дайджеста
        await scheduler.schedule_task(
            "send_digest",
            f"0 {time} */{interval} * *",
            {
                "chat_id": chat_id,
                "action": "digest"
            }
        )
        
    async def crawl_relevant_articles(self, chat_id: str):
        """Поиск и сохранение релевантных статей"""
        storage = self.plugin_manager.get_plugin("storage")
        internet = self.plugin_manager.get_plugin("internet")
        
        # Получаем предпочтения пользователя
        prefs = await storage.search({
            "key_prefix": "preferences/",
            "latest_only": True,
            "tags": [f"user_{chat_id}"]
        })
        
        if not prefs:
            logger.error(f"Preferences not found for user {chat_id}")
            return
            
        # Для каждой интересующей темы
        for topic in prefs[0]["value"]["topics"]:
            # Ищем статьи
            results = await internet.execute_tool("search", {
                "query": topic
            })
            
            # Для каждого результата
            for result in results["results"]:
                # Извлекаем контент
                content = await internet.execute_tool("crawl", {
                    "url": result["link"]
                })
                
                if content and not content.get("error"):
                    # Сохраняем статью
                    article_id = storage.generate_id("article", result["title"])
                    await storage.create({
                        "key": article_id,
                        "value": {
                            "title": result["title"],
                            "content": content["content"],
                            "url": result["link"]
                        },
                        "metadata": {
                            "type": "article",
                            "topic": topic,
                            "user_id": chat_id,
                            "created_at": datetime.now().isoformat()
                        }
                    })
                    
    async def generate_digest(self, chat_id: str) -> str:
        """Генерирует дайджест на основе сохраненных статей"""
        storage = self.plugin_manager.get_plugin("storage")
        
        # Получаем статьи за последний период
        articles = await storage.search({
            "key_prefix": "article/",
            "latest_only": True,
            "tags": [f"user_{chat_id}"]
        })
        
        if not articles:
            return "Не найдено новых статей для дайджеста"
            
        # Группируем по темам
        topics = {}
        for article in articles:
            topic = article["metadata"]["topic"]
            if topic not in topics:
                topics[topic] = []
            topics[topic].append(article)
            
        # Формируем дайджест
        digest = "# 📰 Ваш персональный дайджест\n\n"
        
        for topic, articles in topics.items():
            digest += f"## {topic}\n\n"
            for article in articles:
                digest += f"### [{article['value']['title']}]({article['value']['url']})\n"
                digest += f"{article['value']['content'][:200]}...\n\n"
                
        return digest


async def handle_message(message: IOMessage, agent: DigestAgent, telegram: TelegramPlugin):
    """Обработка входящего сообщения"""
    if message.type != "telegram_message":
        return
        
    chat_id = message.metadata["chat_id"]
    
    # Отправляем typing...
    await telegram.output_hook(
        IOMessage(
            type="action",
            content="typing",
            metadata={"chat_id": chat_id}
        )
    )
    
    try:
        # Если интервью не завершено
        if not agent.interview_completed:
            # Обрабатываем ответ и получаем следующий вопрос
            response = await agent.process_message(
                message=message.content,
                system_prompt=INTERVIEW_PROMPT
            )
            
            # Если это последний вопрос
            if "save_preferences" in response:
                # Сохраняем предпочтения
                prefs_id = await agent.save_preferences(chat_id)
                
                # Настраиваем расписание
                time = agent.interview_data.get("preferred_time", "10:00")
                interval = agent.interview_data.get("digest_interval", "1")
                await agent.setup_digest_schedule(chat_id, time, interval)
                
                agent.interview_completed = True
                response = "Спасибо за ответы! Я настроил персональный дайджест согласно вашим предпочтениям. Первый выпуск придет в указанное время."
                
        else:
            # Обычный режим работы
            response = await agent.process_message(
                message=message.content,
                system_prompt=DIGEST_PROMPT
            )
            
        # Отправляем ответ
        await telegram.output_hook(
            IOMessage(
                type="message",
                content=response,
                metadata={"chat_id": chat_id}
            )
        )
            
    except Exception as e:
        logger.error(f"Error processing message: {e}")
        await telegram.output_hook(
            IOMessage(
                type="message",
                content="Извините, произошла ошибка при обработке сообщения.",
                metadata={"chat_id": chat_id}
            )
        )


async def handle_scheduled_task(task: Dict[str, Any], agent: DigestAgent, telegram: TelegramPlugin):
    """Обработка запланированной задачи"""
    chat_id = task["params"]["chat_id"]
    action = task["params"]["action"]
    
    try:
        if action == "crawl":
            await agent.crawl_relevant_articles(chat_id)
            
        elif action == "digest":
            digest = await agent.generate_digest(chat_id)
            await telegram.output_hook(
                IOMessage(
                    type="message",
                    content=digest,
                    metadata={"chat_id": chat_id}
                )
            )
            
    except Exception as e:
        logger.error(f"Error processing scheduled task: {e}")


async def setup_agent(llm) -> DigestAgent:
    """Создание и настройка агента"""
    if not config.telegram_token:
        raise ValueError("Telegram token not provided in config")
        
    # Создаем агента
    agent = DigestAgent(llm=llm)
    
    # Создаем и регистрируем плагины
    telegram = TelegramPlugin()
    scheduler = SchedulerPlugin(
        tick_interval=1.0,
        timezone=str(get_timezone())
    )
    storage = VersionedStoragePlugin()
    internet = InternetPlugin(
        max_search_results=10,
        min_word_count=50
    )
    
    # Инициализируем плагины
    await telegram.setup(token=config.telegram_token)
    await scheduler.setup()
    await storage.setup()
    await internet.setup()
    
    # Регистрируем плагины
    agent.plugin_manager.register_plugin("telegram", telegram)
    agent.plugin_manager.register_plugin("scheduler", scheduler)
    agent.plugin_manager.register_plugin("storage", storage)
    agent.plugin_manager.register_plugin("internet", internet)
    
    # Устанавливаем обработчики
    telegram.message_handler = lambda msg: handle_message(msg, agent, telegram)
    scheduler.task_handler = lambda task: handle_scheduled_task(task, agent, telegram)
    
    # Отправляем приветственное сообщение
    user_id = "test_user"
    chat_id = await telegram.check_chat_link(user_id)
    
    if chat_id:
        print(f"\n✅ Уже есть привязка к чату: {chat_id}")
        await telegram.output_hook(
            IOMessage(
                type="message",
                content="Привет! Я помогу настроить персональный дайджест. Давайте начнем с нескольких вопросов о ваших интересах.",
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