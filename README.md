# CogniStruct

Модульный фреймворк для создания AI-ассистентов с поддержкой плагинов.

## Особенности

- 🔌 Модульная архитектура на основе плагинов
- 🧠 Поддержка различных LLM (OpenAI, DeepSeek, Ollama)
- 🛠 Система инструментов для расширения возможностей
- 💾 Краткосрочная и долгосрочная память
- 📅 Планировщик задач
- 🔢 Калькулятор с безопасными вычислениями
- 📱 Интеграция с Telegram

## Установка

```bash
git clone https://github.com/your-username/cognistruct.git
cd cognistruct
pip install -r requirements.txt
```

## Быстрый старт

1. Создайте файл конфигурации:
```bash
cp config.example.yaml config.yaml
```

2. Отредактируйте config.yaml и добавьте ваши API ключи

3. Запустите пример консольного агента:
```bash
python examples/example_simple_agent.py
```

## Плагины

### ShortTermMemory
Хранит контекст последних сообщений для поддержания связного диалога.

```python
memory = ShortTermMemoryPlugin(
    max_messages=15,  # Количество хранимых сообщений (примерно 7-8 обменов репликами)
    db_path="data/chat_memory.db"  # Опционально: путь к файлу базы данных
)
```

Плагин автоматически:
- Сохраняет входящие и исходящие сообщения
- Поддерживает ограниченное количество сообщений
- Добавляет историю диалога в контекст для LLM
- Удаляет старые сообщения при добавлении новых
- Хранит сообщения в SQLite базе данных

Параметры:
- `max_messages`: количество хранимых сообщений
- `db_path`: путь к файлу базы данных (по умолчанию "data/short_term_memory.db")

Пример использования контекста:
```python
User: Какой язык программирования мы обсуждали?
Assistant: Судя по нашей предыдущей беседе, мы обсуждали Python в контексте асинхронного программирования.
```

### Calculator
Безопасное выполнение математических вычислений.

```python
calculator = CalculatorPlugin()
# Использование: "calculate 2 + 2"
```

### Scheduler
Планирование и выполнение отложенных задач.

```python
scheduler = SchedulerPlugin(
    tick_interval=1.0,
    timezone="Europe/Moscow"
)
# Использование: "schedule_task ..."
```

### Telegram
Интеграция с Telegram Bot API.

```python
telegram = TelegramPlugin()
await telegram.setup(token="YOUR_BOT_TOKEN")
```

## Создание агента

```python
from agents import BaseAgent
from llm import LLMRouter

# Инициализация LLM
router = LLMRouter()
llm = router.create_instance(
    provider="deepseek",
    api_key="YOUR_API_KEY",
    model="deepseek-chat"
)

# Создание агента
agent = BaseAgent(llm=llm)

# Регистрация плагинов
agent.plugin_manager.register_plugin("memory", memory)
agent.plugin_manager.register_plugin("calculator", calculator)
agent.plugin_manager.register_plugin("scheduler", scheduler)

# Обработка сообщений
response = await agent.process_message(
    message="Привет!",
    system_prompt="Ты - полезный ассистент"
)
```

## Разработка плагинов

Создайте новый плагин, унаследовавшись от BasePlugin:

```python
from plugins.base_plugin import BasePlugin, PluginMetadata

class MyPlugin(BasePlugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my_plugin",
            description="Описание плагина",
            version="1.0.0",
            priority=50
        )
        
    async def setup(self):
        # Инициализация плагина
        pass
        
    def get_tools(self) -> List[Dict[str, Any]]:
        # Описание инструментов
        return []
```

## Лицензия

MIT License
