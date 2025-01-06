import platform
from datetime import datetime
from zoneinfo import ZoneInfo, available_timezones
from typing import Optional

from .logging import setup_logger

logger = setup_logger(__name__)


def get_system_timezone() -> str:
    """
    Определяет часовой пояс системы
    
    Returns:
        str: Идентификатор часового пояса
    """
    try:
        if platform.system() == 'Windows':
            import tzlocal
            return str(tzlocal.get_localzone())
        else:
            # На Unix-системах можно прочитать из /etc/timezone
            with open('/etc/timezone', 'r') as f:
                return f.read().strip()
    except Exception as e:
        logger.warning("Failed to detect system timezone: %s", e)
        
        # Пробуем определить часовой пояс по смещению
        offset = datetime.now().astimezone().utcoffset()
        if offset:
            hours = offset.total_seconds() / 3600
            if hours == 3:  # UTC+3
                return "Europe/Moscow"
            elif hours == 2:  # UTC+2
                return "Europe/Kiev"
            elif hours == 4:  # UTC+4
                return "Europe/Samara"
                
        # Если не удалось определить, используем UTC
        return "UTC"


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