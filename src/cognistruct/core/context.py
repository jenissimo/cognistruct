from typing import Optional
from dataclasses import dataclass


@dataclass
class AppContext:
    """Глобальный контекст приложения"""
    user_id: int = 0  # 0 = дефолтный пользователь
    
    
class GlobalContext:
    """Синглтон для хранения глобального контекста"""
    _instance: Optional[AppContext] = None
    
    @classmethod
    def get(cls) -> AppContext:
        """Получить текущий контекст"""
        if cls._instance is None:
            cls._instance = AppContext()
        return cls._instance
    
    @classmethod
    def set_user_id(cls, user_id: int):
        """Установить текущего пользователя"""
        ctx = cls.get()
        ctx.user_id = user_id
        
    @classmethod
    def reset(cls):
        """Сбросить контекст"""
        cls._instance = None 