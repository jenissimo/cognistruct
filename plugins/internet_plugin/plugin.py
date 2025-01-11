from typing import Dict, Any, List, Optional
import asyncio
import logging
from datetime import datetime
from pathlib import Path

from duckduckgo_search import DDGS
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

from plugins.base_plugin import BasePlugin, PluginMetadata, IOMessage
from llm.interfaces import ToolSchema, ToolParameter

logger = logging.getLogger(__name__)


class InternetPlugin(BasePlugin):
    """
    Плагин для работы с интернетом: поиск и краулинг
    
    Использует:
    - DuckDuckGo для поиска
    - Crawl4AI для извлечения контента
    """
    
    def __init__(self,
                 browser_profile_dir: str = ".crawl4ai/browser_profile",
                 max_search_results: int = 5,
                 min_word_count: int = 20,
                 max_markdown_length: int = 4000):
        super().__init__()
        self.browser_profile_dir = Path(browser_profile_dir)
        self.max_search_results = max_search_results
        self.min_word_count = min_word_count
        self.max_markdown_length = max_markdown_length
        self._ddgs: Optional[DDGS] = None
        self._crawler: Optional[AsyncWebCrawler] = None
        
    def get_metadata(self) -> PluginMetadata:
        return PluginMetadata(
            name="internet",
            description="Поиск и извлечение информации из интернета",
            version="0.1.0",
            author="Cognistruct"
        )
        
    async def setup(self):
        """Инициализация компонентов"""
        await super().setup()
        
        # Создаем директорию для профиля браузера
        self.browser_profile_dir.parent.mkdir(parents=True, exist_ok=True)
        
        # Инициализируем поисковик
        self._ddgs = DDGS()
        
        # Настраиваем краулер с базовой конфигурацией
        browser_config = BrowserConfig(
            verbose=True,  # Включаем логирование
            headless=True  # Браузер без GUI
        )
        
        # Создаем краулер
        self._crawler = AsyncWebCrawler(config=browser_config)
        await self._crawler.__aenter__()
        
    async def cleanup(self):
        """Очистка ресурсов"""
        if self._crawler:
            await self._crawler.__aexit__(None, None, None)
        
    async def search_web(self, query: str) -> List[Dict[str, Any]]:
        """Поиск в интернете через DuckDuckGo"""
        results = []
        try:
            # Используем синхронный API в асинхронном контексте
            loop = asyncio.get_event_loop()
            search_results = await loop.run_in_executor(
                None, 
                lambda: list(self._ddgs.text(query, max_results=self.max_search_results))
            )
            
            for r in search_results:
                # Проверяем наличие всех необходимых полей
                result = {
                    "title": r.get("title", "No title"),
                    "link": r.get("href", r.get("url", "No link")),  # Пробуем href или url
                    "snippet": r.get("body", r.get("snippet", "No description"))  # Пробуем body или snippet
                }
                results.append(result)
                
            logger.info(f"Found {len(results)} results for query: {query}")
            return results
            
        except Exception as e:
            logger.error(f"Search failed: {str(e)}")
            return []
        
    async def crawl_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Извлечение контента с веб-страницы"""
        try:
            # Конфигурация для конкретного запроса
            run_config = CrawlerRunConfig(
                word_count_threshold=self.min_word_count,  # Фильтруем короткие блоки
                exclude_external_links=True,  # Убираем внешние ссылки
                remove_overlay_elements=True,  # Удаляем попапы
                process_iframes=True,  # Обрабатываем iframe
                cache_mode=CacheMode.BYPASS,  # Всегда свежий контент
                fit_markdown=True  # Включаем оптимизированную версию markdown
            )
            
            result = await self._crawler.arun(url, config=run_config)
            
            if not result.success:
                print(f"Ошибка краулинга: {result.error_message}")
                return None
                
            # Сначала пробуем использовать fit_markdown
            markdown_content = result.fit_markdown or result.markdown
            
            # Если всё ещё слишком длинный, обрезаем
            if len(markdown_content) > self.max_markdown_length:
                markdown_content = markdown_content[:self.max_markdown_length] + "\n\n... (контент обрезан из-за ограничения длины)"
                
            return {
                "url": url,
                "content": markdown_content,
                "links": {
                    "internal": result.links.get("internal", [])
                },
                "crawled_at": datetime.now().isoformat()
            }
            
        except Exception as e:
            print(f"Ошибка при краулинге {url}: {e}")
            return None
        
    def get_tools(self) -> List[ToolSchema]:
        """Возвращает инструменты для работы с интернетом"""
        return [
            ToolSchema(
                name="search",
                description="Ищет информацию в интернете для твоей дальнейшей обработки",
                parameters=[
                    ToolParameter(
                        name="query",
                        type="string",
                        description="Поисковый запрос"
                    )
                ]
            ),
            ToolSchema(
                name="crawl",
                description="Получает контента веб-страницы в формате Markdown со ссылками для твоей дальнейшей обработки",
                parameters=[
                    ToolParameter(
                        name="url",
                        type="string",
                        description="URL страницы для извлечения контента"
                    )
                ]
            )
        ]
        
    async def execute_tool(self, tool_name: str, params: Dict[str, Any]) -> Any:
        """Выполняет инструменты"""
        if tool_name == "search":
            results = await self.search_web(params["query"])
            return {
                "message": f"Найдено {len(results)} результатов",
                "results": results
            }
            
        elif tool_name == "crawl":
            content = await self.crawl_url(params["url"])
            if not content:
                return {"error": "Не удалось извлечь контент"}
            return content
            
        return {"error": f"Неизвестный инструмент: {tool_name}"} 