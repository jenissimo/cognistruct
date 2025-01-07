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
- 🎨 Поддержка Markdown в консоли

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

### ConsolePlugin
Обработка консольного ввода/вывода с поддержкой Markdown.

```python
console = ConsolePlugin(
    prompt="👤 ",                    # Строка приглашения ввода
    exit_command="exit",             # Команда для выхода
    exit_message="\n👋 До свидания!", # Сообщение при выходе
    use_markdown=True,               # Включить форматирование Markdown
    use_emojis=True                  # Использовать эмодзи
)

# Регистрация обработчика сообщений
async def handle_message(message: IOMessage):
    await agent.process_message(message.content)

console.set_message_handler(handle_message)
```

### ShortTermMemory
Хранит контекст последних сообщений для поддержания связного диалога.

```python
memory = ShortTermMemoryPlugin(
    max_messages=15  # Количество хранимых сообщений (примерно 7-8 обменов репликами)
)
```

Плагин автоматически:
- Сохраняет входящие и исходящие сообщения
- Поддерживает ограниченное количество сообщений
- Добавляет историю диалога в контекст для LLM
- Удаляет старые сообщения при добавлении новых
- Хранит сообщения в SQLite базе данных

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

## Создание агента

```python
from agents import BaseAgent
from llm import LLMRouter
from plugins.console_plugin import ConsolePlugin

# Инициализация LLM
router = LLMRouter()
llm = router.create_instance(
    provider="deepseek",
    api_key="YOUR_API_KEY",
    model="deepseek-chat"
)

# Создание агента
agent = BaseAgent(llm=llm)

# Создание и настройка плагинов
console = ConsolePlugin(use_markdown=True)
memory = ShortTermMemoryPlugin(max_messages=15)

# Регистрация плагинов
agent.plugin_manager.register_plugin("console", console)
agent.plugin_manager.register_plugin("memory", memory)

# Запуск агента
await agent.start()

# Запуск консольного интерфейса
await console.start()
```

## Разработка плагинов

Создайте новый плагин, унаследовавшись от BasePlugin:

```python
from plugins.base_plugin import BasePlugin, PluginMetadata, IOMessage

class MyPlugin(BasePlugin):
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="my_plugin",
            description="Описание плагина",
            version="1.0.0",
            priority=50
        )
        
    async def input_hook(self, message: IOMessage) -> bool:
        """Обработка входящих сообщений"""
        return False
        
    async def output_hook(self, message: IOMessage):
        """Обработка исходящих сообщений"""
        pass
```

## Лицензия

MIT License
