from utils import Config, setup_logger


logger = setup_logger(__name__)


def main():
    logger.info("Настройка Cognistruct")
    logger.info("---------------------")
    
    api_key = input("Введите ваш DeepSeek API ключ: ").strip()
    
    config = Config(deepseek_api_key=api_key)
    config.save()
    
    logger.info("Конфигурация сохранена!")
    logger.info("Теперь вы можете запустить test_agent.py для проверки работы")


if __name__ == "__main__":
    main() 