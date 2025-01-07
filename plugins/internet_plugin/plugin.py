from typing import Dict, Any, List, Optional
import asyncio
from datetime import datetime
from pathlib import Path

from duckduckgo_search import AsyncDDGS
from crawl4ai import AsyncWebCrawler, BrowserConfig, CrawlerRunConfig, CacheMode

from plugins.base_plugin import BasePlugin, PluginMetadata, IOMessage
from llm.interfaces import ToolSchema, ToolParameter


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
                 min_word_count: int = 20):
        super().__init__()
        self.browser_profile_dir = Path(browser_profile_dir)
        self.max_search_results = max_search_results
        self.min_word_count = min_word_count
        self._ddgs: Optional[AsyncDDGS] = None
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
        self._ddgs = AsyncDDGS()
        
        # Настраиваем краулер
        browser_config = BrowserConfig(
            verbose=True,
            headless=True,
            user_data_dir=str(self.browser_profile_dir),
            use_persistent_context=True
        )
        self._crawler = AsyncWebCrawler(config=browser_config)
        await self._crawler.__aenter__()
        
    async def cleanup(self):
        """Очистка ресурсов"""
        if self._crawler:
            await self._crawler.__aexit__(None, None, None)
        
    async def search_web(self, query: str) -> List[Dict[str, Any]]:
        """Поиск в интернете через DuckDuckGo"""
        results = []
        async for r in self._ddgs.text(query, max_results=self.max_search_results):
            results.append({
                "title": r["title"],
                "link": r["link"],
                "snippet": r["body"]
            })
        return results
        
    async def crawl_url(self, url: str) -> Optional[Dict[str, Any]]:
        """Извлечение контента с веб-страницы"""
        try:
            run_config = CrawlerRunConfig(
                word_count_threshold=self.min_word_count,  # Фильтруем короткие блоки
                exclude_external_links=False,  # Сохраняем внешние ссылки
                remove_overlay_elements=True,  # Удаляем попапы
                process_iframes=True,  # Обрабатываем iframe
                cache_mode=CacheMode.BYPASS  # Всегда свежий контент
            )
            
            result = await self._crawler.arun(url, config=run_config)
            
            if not result.success:
                print(f"Ошибка краулинга: {result.error_message}")
                return None
                
            return {
                "url": url,
                "content": result.markdown,
                "links": {
                    "internal": result.links.get("internal", []),
                    "external": result.links.get("external", [])
                },
                "media": result.media,
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
                description="Поиск информации в интернете через DuckDuckGo",
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
                description="Извлечение контента веб-страницы в формате Markdown со ссылками",
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