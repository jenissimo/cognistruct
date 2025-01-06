from typing import Dict, Optional, Type

from llm.interfaces import BaseLLM
from llm.deepseek_service import DeepSeekLLM, DeepSeekConfig
from utils.logging import setup_logger

logger = setup_logger(__name__)


class LLMRouter:
    """Роутер для работы с различными LLM провайдерами"""
    
    def __init__(self):
        self._providers: Dict[str, Type[BaseLLM]] = {
            "deepseek": DeepSeekLLM
        }
        self._instances: Dict[str, BaseLLM] = {}
        logger.info("LLMRouter initialized with providers: %s", list(self._providers.keys()))

    def register_provider(self, name: str, provider: Type[BaseLLM]):
        """Регистрирует нового провайдера LLM"""
        self._providers[name] = provider
        logger.info("Registered new LLM provider: %s", name)

    def get_instance(self, provider: str) -> Optional[BaseLLM]:
        """Возвращает экземпляр LLM по имени провайдера"""
        instance = self._instances.get(provider)
        if instance:
            logger.debug("Retrieved existing LLM instance: %s", provider)
        else:
            logger.debug("No existing instance found for provider: %s", provider)
        return instance

    def create_instance(self, provider: str, config: dict) -> BaseLLM:
        """Создает новый экземпляр LLM"""
        if provider not in self._providers:
            logger.error("Attempted to create instance with unknown provider: %s", provider)
            raise ValueError(f"Unknown LLM provider: {provider}")
            
        provider_class = self._providers[provider]
        
        if provider == "deepseek":
            config = DeepSeekConfig(**config)
            
        instance = provider_class(config)
        self._instances[provider] = instance
        logger.info("Created new LLM instance for provider: %s", provider)
        return instance

    async def close_all(self):
        """Закрывает все активные соединения"""
        logger.info("Closing all LLM connections...")
        for provider, instance in self._instances.items():
            if hasattr(instance, 'close'):
                logger.debug("Closing connection for provider: %s", provider)
                await instance.close()
        self._instances.clear()
        logger.info("All LLM connections closed") 