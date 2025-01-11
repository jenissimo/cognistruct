"""CogniStruct - модульный фреймворк для создания AI-ассистентов с поддержкой плагинов"""

__version__ = "0.1.0"

# Основные классы для удобного импорта
from cognistruct.core import BaseAgent, BasePlugin, PluginMetadata
from cognistruct.utils.prompts import prompt_manager
from cognistruct.utils.pipeline import Stage, StageChain 