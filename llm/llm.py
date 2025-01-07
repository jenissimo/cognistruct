from typing import Dict, Optional, Type

from llm.interfaces import BaseLLM
from llm.openai_service import OpenAIService, OpenAIProvider, OPENAI, DEEPSEEK, OLLAMA
from utils.logging import setup_logger

logger = setup_logger(__name__)


class LLMRouter:
    """Роутер для работы с различными LLM провайдерами"""
    
    def __init__(self):
        # Предопределенные провайдеры
        self._providers = {
            "openai": OPENAI,
            "deepseek": DEEPSEEK,
            "ollama": OLLAMA
        }
        self._instances: Dict[str, BaseLLM] = {}
        logger.info("LLMRouter initialized with providers: %s", list(self._providers.keys()))

    def register_provider(self, name: str, provider: OpenAIProvider):
        """Регистрирует нового провайдера"""
        self._providers[name] = provider
        logger.info("Registered new provider: %s", name)

    def get_instance(self, provider: str) -> Optional[BaseLLM]:
        """Возвращает экземпляр LLM по имени провайдера"""
        return self._instances.get(provider)

    def create_instance(self, provider: str, api_key: str, model: Optional[str] = None) -> BaseLLM:
        """
        Создает новый экземпляр LLM
        
        Args:
            provider: Имя провайдера (openai, deepseek, ollama или кастомный)
            api_key: API ключ (для Ollama можно пустой)
            model: Название модели (обязательно для Ollama, опционально для других)
        """
        if provider not in self._providers:
            raise ValueError(f"Unknown provider: {provider}")
            
        # Создаем копию конфигурации провайдера
        provider_config = self._providers[provider]
        config = OpenAIProvider(
            name=provider_config.name,
            model=model or provider_config.model,  # Используем указанную модель или дефолтную
            api_base=provider_config.api_base,
            api_key=api_key
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