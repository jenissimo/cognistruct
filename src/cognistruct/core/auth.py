from abc import ABC, abstractmethod
from typing import Dict, Any, Optional, Type
import logging

from .context import RequestContext

logger = logging.getLogger(__name__)


class AuthProvider(ABC):
    """
    Базовый класс для провайдеров аутентификации.
    Определяет интерфейс для аутентификации пользователей и валидации их идентификаторов.
    """

    @abstractmethod
    async def authenticate(self, credentials: Dict[str, Any]) -> str:
        """
        Аутентифицирует пользователя по переданным credentials.
        Возвращает user_id в случае успеха.
        Выбрасывает AuthError в случае ошибки.
        """
        pass

    @abstractmethod
    async def validate(self, user_id: str) -> bool:
        """
        Проверяет валидность user_id.
        Возвращает True если user_id валиден.
        """
        pass

    async def create_context(self, credentials: Dict[str, Any]) -> RequestContext:
        """
        Создает контекст запроса после успешной аутентификации.
        """
        user_id = await self.authenticate(credentials)
        return RequestContext(
            user_id=user_id,
            metadata={"auth_provider": self.__class__.__name__, **credentials}
        )


class AuthError(Exception):
    """Базовый класс для ошибок аутентификации"""
    pass


class InvalidCredentialsError(AuthError):
    """Ошибка невалидных credentials"""
    pass


class UserNotFoundError(AuthError):
    """Ошибка отсутствия пользователя"""
    pass


class AuthProviderFactory:
    """
    Фабрика для создания провайдеров аутентификации.
    Позволяет регистрировать и получать провайдеры по имени.
    """
    _providers: Dict[str, Type[AuthProvider]] = {}

    @classmethod
    def register(cls, name: str, provider: Type[AuthProvider]):
        """Регистрирует провайдер аутентификации"""
        cls._providers[name] = provider
        logger.info(f"Registered auth provider: {name}")

    @classmethod
    def create(cls, name: str, **kwargs) -> Optional[AuthProvider]:
        """Создает инстанс провайдера по имени"""
        provider_cls = cls._providers.get(name)
        if not provider_cls:
            logger.error(f"Auth provider not found: {name}")
            return None
            
        return provider_cls(**kwargs) 