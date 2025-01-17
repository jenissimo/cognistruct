from typing import Dict, Optional, Type

from cognistruct.llm.interfaces import BaseLLM
from cognistruct.llm.openai_service import OpenAIService, OpenAIProvider, OPENAI, DEEPSEEK, OLLAMA, PROXYAPI
from cognistruct.utils.logging import setup_logger

logger = setup_logger(__name__)


class LLMRouter:
    """Роутер для работы с различными LLM провайдерами"""
    
    def __init__(self):
        # Предопределенные провайдеры
        self._providers = {
            "openai": OPENAI,
            "proxyapi": PROXYAPI,
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

    def create_instance(self, provider: str, api_key: str, model: Optional[str] = None, 
                     temperature: Optional[float] = None, max_tokens: Optional[int] = None) -> BaseLLM:
        """
        Создает новый экземпляр LLM
        
        Args:
            provider: Имя провайдера (openai, deepseek, ollama или кастомный)
            api_key: API ключ (для Ollama можно пустой)
            model: Название модели (обязательно для Ollama, опционально для других)
            temperature: Температура генерации (0.0 - 1.0)
            max_tokens: Максимальное количество токенов в ответе
        """
        if provider not in self._providers:
            raise ValueError(f"Unknown provider: {provider}")
            
        # Создаем копию конфигурации провайдера
        provider_config = self._providers[provider]
        config = OpenAIProvider(
            name=provider_config.name,
            model=model or provider_config.model,  # Используем указанную модель или дефолтную
            api_base=provider_config.api_base,
            api_key=api_key,
            temperature=temperature if temperature is not None else provider_config.temperature,
            max_tokens=max_tokens if max_tokens is not None else provider_config.max_tokens
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