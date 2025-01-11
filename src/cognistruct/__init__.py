"""CogniStruct - модульный фреймворк для создания AI-ассистентов с поддержкой плагинов"""

__version__ = "0.1.0"

# Основные классы для удобного импорта
from .core import BaseAgent, BasePlugin, PluginMetadata
from .utils.prompts import prompt_manager
from .utils.pipeline import Stage, StageChain 