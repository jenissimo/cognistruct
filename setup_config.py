from utils import Config, setup_logger


logger = setup_logger(__name__)


def main():
    logger.info("Настройка Cognistruct")
    logger.info("---------------------")
    
    # Пробуем загрузить существующую конфигурацию
    try:
        current_config = Config.load()
        has_api_key = bool(current_config.deepseek_api_key)
        has_proxy_key = bool(current_config.proxyapi_key)
        has_telegram = bool(current_config.telegram_token)
        has_admin = bool(current_config.admin_username)
        
        if has_api_key:
            logger.info("Найден существующий DeepSeek API ключ")
        if has_proxy_key:
            logger.info("Найден существующий ProxyAPI ключ")
        if has_telegram:
            logger.info("Найден существующий Telegram токен")
        if has_admin:
            logger.info("Найдены существующие админ-креденшлы для REST API")
    except:
        current_config = None
        has_api_key = False
        has_proxy_key = False
        has_telegram = False
        has_admin = False
    
    # Запрашиваем новые значения
    api_key = input("Введите ваш DeepSeek API ключ" + (" (Enter чтобы оставить текущий)" if has_api_key else "") + ": ").strip()
    proxy_key = input("Введите ваш ProxyAPI ключ" + (" (Enter чтобы оставить текущий)" if has_proxy_key else " (опционально)") + ": ").strip()
    telegram_token = input("Введите токен Telegram бота" + (" (Enter чтобы оставить текущий)" if has_telegram else " (опционально)") + ": ").strip()
    
    # Запрашиваем админские креденшлы для REST API
    admin_username = input("Введите имя пользователя для REST API" + (" (Enter чтобы оставить текущий)" if has_admin else "") + ": ").strip()
    admin_password = input("Введите пароль для REST API" + (" (Enter чтобы оставить текущий)" if has_admin else "") + ": ").strip()
    
    # Сохраняем старые значения если ввод пустой
    if has_api_key and not api_key:
        api_key = current_config.deepseek_api_key
    if has_proxy_key and not proxy_key:
        proxy_key = current_config.proxyapi_key
    if has_telegram and not telegram_token:
        telegram_token = current_config.telegram_token
    if has_admin and not admin_username:
        admin_username = current_config.admin_username
        admin_password = current_config.admin_password
    
    config = Config(
        deepseek_api_key=api_key,
        proxyapi_key=proxy_key if proxy_key else None,
        telegram_token=telegram_token if telegram_token else None,
        admin_username=admin_username if admin_username else None,
        admin_password=admin_password if admin_password else None
    )
    config.save()
    
    logger.info("Конфигурация сохранена!")
    if telegram_token:
        logger.info("Для использования Telegram бота запустите example_telegram_agent.py")
    else:
        logger.info("Для базового тестирования запустите example_simple_agent.py")
    
    if admin_username and admin_password:
        logger.info(f"REST API доступен с креденшлами: {admin_username}:{'*' * len(admin_password)}")


if __name__ == "__main__":
    main() 