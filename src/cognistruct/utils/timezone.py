import platform
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones
from typing import Optional
import tzlocal
from .logging import setup_logger

logger = setup_logger(__name__)


def get_system_timezone() -> str:
    """
    Определяет часовой пояс системы
    
    Returns:
        str: Идентификатор часового пояса
    """
    return str(tzlocal.get_localzone())


def validate_timezone(timezone: str) -> str:
    """
    Проверяет и возвращает корректный часовой пояс
    
    Args:
        timezone: Идентификатор часового пояса
        
    Returns:
        str: Валидный идентификатор часового пояса
    """
    if timezone in available_timezones():
        return timezone
        
    # Если указанный часовой пояс не найден, пробуем найти альтернативу
    if timezone == "Europe/Moscow":
        alternatives = ["Europe/Kirov", "Europe/Volgograd", "UTC"]
    elif timezone == "Europe/Kiev":
        alternatives = ["Europe/Bucharest", "Europe/Chisinau", "UTC"]
    else:
        alternatives = ["UTC"]
        
    # Проверяем альтернативы
    for alt in alternatives:
        if alt in available_timezones():
            logger.info("Using alternative timezone %s instead of %s", alt, timezone)
            return alt
            
    return "UTC"


def get_timezone(timezone: Optional[str] = None) -> ZoneInfo:
    """
    Получает объект ZoneInfo для указанного или системного часового пояса
    
    Args:
        timezone: Идентификатор часового пояса (опционально)
        
    Returns:
        ZoneInfo: Объект часового пояса
    """
    if timezone is None:
        timezone = get_system_timezone()
    timezone = validate_timezone(timezone)
    return ZoneInfo(timezone) 