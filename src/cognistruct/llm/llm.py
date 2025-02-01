from typing import Dict, Optional, Type

from .interfaces import BaseLLM
from .openai_service import OpenAIService, OpenAIProvider, OPENAI, DEEPSEEK, OLLAMA, PROXYAPI
from ..utils.logging import setup_logger

logger = setup_logger(__name__)


class LLMRouter:
    """Роутер для работы с различными LLM провайдерами"""
    
    def __init__(self):
        # Предопределенные провайдеры с дефолтными настройками
        self._default_settings = {
            OPENAI: {
                "model": "gpt-4o",
                "base_url": "https://api.openai.com/v1"
            },
            PROXYAPI: {
                "model": "gpt-4o",
                "base_url": "https://api.proxyapi.ru/openai/v1"
            },
            DEEPSEEK: {
                "model": "deepseek-chat",
                "base_url": "https://api.deepseek.com/v1"
            },
            OLLAMA: {
                "model": "llama2",  # Дефолтная модель
                "base_url": "http://localhost:11434/v1"
            }
        }
        self._instances: Dict[str, BaseLLM] = {}
        logger.info("LLMRouter initialized with providers: %s", list(self._default_settings.keys()))

    def register_provider(self, name: str, settings: Dict[str, str]):
        """Регистрирует нового провайдера"""
        self._default_settings[name] = settings
        logger.info("Registered new provider: %s", name)

    def get_instance(self, provider: str) -> Optional[BaseLLM]:
        """Возвращает экземпляр LLM по имени провайдера"""
        return self._instances.get(provider)

    def create_instance(
        self, 
        provider: str, 
        api_key: str, 
        model: Optional[str] = None, 
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None
    ) -> BaseLLM:
        """
        Создает новый экземпляр LLM
        
        Args:
            provider: Имя провайдера (openai, deepseek, ollama или кастомный)
            api_key: API ключ (для Ollama можно пустой)
            model: Название модели (обязательно для Ollama, опционально для других)
            temperature: Температура генерации (0.0 - 1.0)
            max_tokens: Максимальное количество токенов в ответе
        """
        if provider not in self._default_settings:
            raise ValueError(f"Unknown provider: {provider}")
            
        # Получаем дефолтные настройки
        settings = self._default_settings[provider]
        
        # Создаем конфигурацию провайдера
        config = OpenAIProvider(
            api_key=api_key,
            model=model or settings["model"],
            base_url=settings["base_url"],
            temperature=temperature or 0.7,
            provider=provider,
            max_tokens=max_tokens
        )
            
        # Создаем экземпляр сервиса
        instance = OpenAIService(config)
        self._instances[provider] = instance
        logger.info("Created new instance for provider: %s with model: %s", 
                   provider, config.model)
        return instance

    async def close_all(self):
        """Закрывает все активные соединения"""
        logger.info("Closing all LLM connections...")
        for provider, instance in self._instances.items():
            await instance.close()
        self._instances.clear()
        logger.info("All LLM connections closed") 