import json
from typing import Any, Dict, List, Optional, Union, AsyncGenerator
from dataclasses import dataclass
import asyncio

from openai import AsyncOpenAI
from pydantic import BaseModel

from cognistruct.llm.interfaces import BaseLLM, LLMResponse, ToolSchema, ToolCall
from cognistruct.utils.logging import setup_logger
from cognistruct.utils.schema_converter import convert_tool_schema
from cognistruct.core.messages import IOMessage
from cognistruct.llm.tool_call_manager import ToolCallManager, ToolCallBuilder

logger = setup_logger(__name__)

@dataclass
class OpenAIProvider:
    """Конфигурация провайдера OpenAI API"""
    name: str
    model: str
    api_base: str
    api_key: Optional[str] = None  # Может быть None для некоторых провайдеров
    temperature: float = 0.7  # Добавляем температуру по умолчанию
    max_tokens: Optional[int] = None  # Максимальное количество токенов
    is_proxy: bool = False  # Флаг использования ProxyAPI


# Предопределенные провайдеры
OPENAI = OpenAIProvider(
    name="openai",
    model="gpt-4o",
    api_base="https://api.openai.com/v1",
    api_key="",  # Заполняется из конфига
    temperature=0.7,
    max_tokens=None,
    is_proxy=False
)

PROXYAPI = OpenAIProvider(
    name="proxyapi",
    model="gpt-4o",
    api_base="https://api.proxyapi.ru/openai/v1",
    api_key="",  # Заполняется из конфига
    temperature=0.7,
    max_tokens=None,
    is_proxy=True
)

DEEPSEEK = OpenAIProvider(
    name="deepseek",
    model="deepseek-chat",
    api_base="https://api.deepseek.com/v1",
    api_key="",  # Заполняется из конфига
    temperature=0.7,
    max_tokens=None,
    is_proxy=False
)

OLLAMA = OpenAIProvider(
    name="ollama",
    model="",  # Заполняется пользователем
    api_base="http://localhost:11434/v1",
    api_key=None,  # Не требуется для локального Ollama
    temperature=0.7,
    max_tokens=None,
    is_proxy=False
)


class OpenAIService(BaseLLM):
    """Реализация для работы с OpenAI-совместимыми API"""

    def __init__(self, provider: OpenAIProvider):
        self.provider = provider
        self.max_iterations = 5  # Максимальное количество итераций
        
        # Для Ollama не требуется API ключ
        if provider.name == "ollama":
            api_key = "ollama"
            logger.info(f"Initialized provider '{provider.name}' without API key.")
        else:
            if not provider.api_key:
                logger.error(f"API key must be provided for provider '{provider.name}'.")
                raise ValueError(f"API key must be provided for provider '{provider.name}'")
            
            api_key = provider.api_key
            logger.info(f"Initialized provider '{provider.name}' with provided API key.")

        self.client = AsyncOpenAI(
            api_key=api_key,
            base_url=provider.api_base
        )

    def set_tool_executor(self, executor):
        """Устанавливает функцию для выполнения инструментов"""
        self.tool_executor = executor

    async def _generate_regular_response(
        self,
        request_params: Dict[str, Any]
    ) -> IOMessage:
        """Генерирует обычный (не потоковый) ответ"""
        messages = request_params.get("messages", []).copy()
        final_content = ""
        tool_results = []
        
        # Создаем локальный tool_manager для этого запроса
        tool_manager = ToolCallManager()
        if hasattr(self, 'tool_executor'):
            tool_manager.set_tool_executor(self.tool_executor)
        
        for iteration in range(self.max_iterations):
            try:
                # Обновляем параметры запроса
                current_request = request_params.copy()
                current_request["messages"] = messages
                current_request["temperature"] = self.provider.temperature
                
                response = await self.client.chat.completions.create(**current_request)
                message = response.choices[0].message
                message_dict = message.model_dump()
                logger.debug(f"Received response from API: {message_dict}")
                
                # Проверяем наличие tool_calls
                tool_calls = message_dict.get('tool_calls', [])
                if tool_calls and len(tool_calls) > 0:
                    logger.debug(f"Processing {len(tool_calls)} tool calls")
                    # Используем ToolCallBuilder для каждого tool call
                    processed_calls = []
                    for call in tool_calls:
                        # Создаем билдер напрямую из tool call
                        processed_call = ToolCallBuilder.create(call).build()
                        processed_calls.append(processed_call)
                        logger.debug(f"Built tool call: {processed_call}")
                    
                    # Обрабатываем инструменты через менеджер
                    if processed_calls:
                        results = await tool_manager.process_tool_calls(processed_calls, messages)
                        tool_results.extend(results)
                        messages.extend([
                            {"role": "assistant", "content": None, "tool_calls": processed_calls},
                            *[{"role": "tool", "content": result.result.get("content"), "tool_call_id": result.call["id"]} for result in results]
                        ])
                        logger.debug("Updated messages with tool results")
                        continue
                
                # Если нет tool_calls или они пустые, значит это финальный ответ
                final_content = message_dict.get('content', '')
                logger.debug(f"Final content: {final_content}")
                break
                
            except Exception as e:
                logger.error("API request failed: %s", str(e))
                raise RuntimeError(f"API request failed: {str(e)}")
        
        if iteration >= self.max_iterations:
            error_msg = f"Reached maximum number of iterations ({self.max_iterations})"
            logger.warning(error_msg)
            final_content = error_msg
            
        # Создаем IOMessage с результатом
        response = IOMessage(
            type="text",
            content=final_content,
            source="llm"
        )
        
        # Добавляем информацию о вызванных инструментах
        for result in tool_results:
            response.add_tool_call(
                tool_name=result.call["function"]["name"],
                args=json.loads(result.call["function"]["arguments"]),
                result=result.result.get("content"),
                tool_id=result.call["id"]
            )
        
        return response

    async def generate_response(
        self,
        messages: List[Dict[str, Any]],
        tools: Optional[List[ToolSchema]] = None,
        temperature: float = 0.7,
        stream: bool = False,
        **kwargs
    ) -> Union[LLMResponse, AsyncGenerator[IOMessage, None]]:
        """Генерирует ответ, при необходимости выполняя инструменты"""
        logger.debug("OpenAIService.generate_response called with stream=%s", stream)
        
        request_params = {
            "model": self.provider.model,
            "messages": messages,
            "temperature": temperature,
            "stream": stream,
            **kwargs
        }
        logger.debug("Initial request params: %s", request_params)

        # Добавляем max_tokens если он указан в провайдере
        if self.provider.max_tokens is not None:
            request_params["max_tokens"] = self.provider.max_tokens
            logger.debug("Added max_tokens=%d", self.provider.max_tokens)

        # Для ProxyAPI всегда добавляем max_tokens чтобы контролировать стоимость
        if self.provider.is_proxy and "max_tokens" not in request_params:
            request_params["max_tokens"] = 1000  # Разумное ограничение по умолчанию
            logger.debug("Added default max_tokens=1000 for ProxyAPI")

        if tools:
            request_params["tools"] = convert_tool_schema(tools)
            # Используем "none" по умолчанию, чтобы модель не использовала инструменты без необходимости
            request_params["tool_choice"] = kwargs.get("tool_choice", "auto")
            logger.debug("Added %d tools and tool_choice=%s", len(tools), request_params["tool_choice"])

        request_params["temperature"] = temperature
        logger.debug("Final request params: %s", request_params)

        if stream:
            logger.debug("Starting stream response generation")
            return self._generate_stream_response(request_params)
        else:
            logger.debug("Starting regular response generation")
            return await self._generate_regular_response(request_params)

    async def close(self):
        """Закрывает соединение с API"""
        if hasattr(self.client, 'close'):
            await self.client.close()
        elif hasattr(self.client.http_client, 'aclose'):
            await self.client.http_client.aclose()

    async def _generate_stream_response(
        self, 
        request_params: Dict[str, Any]
    ) -> AsyncGenerator[IOMessage, None]:
        """Генерирует streaming ответ"""
        try:
            logger.debug(f"Starting stream response generation")
            current_content = ""
            current_tool_builder = None
            
            # Создаем локальный tool_manager для этого запроса
            tool_manager = ToolCallManager()
            if hasattr(self, 'tool_executor'):
                tool_manager.set_tool_executor(self.tool_executor)
            
            for iteration in range(self.max_iterations):
                logger.debug(f"Iteration {iteration + 1}/{self.max_iterations}")
                
                # Создаем стрим
                stream = await self.client.chat.completions.create(**request_params)
                logger.debug(f"Stream created successfully, type: {type(stream)}")
                logger.debug("Starting to process stream chunks")
                
                async for chunk in stream:
                    if not chunk.choices:
                        logger.debug("Received chunk without choices")
                        continue
                        
                    delta = chunk.choices[0].delta
                    logger.debug(f"Received delta: {delta}")
                    
                    # Пропускаем пустые дельты в начале
                    if not delta.content and not delta.tool_calls and delta.role == 'assistant':
                        logger.debug("Skipping initial empty delta")
                        continue
                    
                    # Обрабатываем контент если есть
                    if delta.content:
                        current_content += delta.content
                        chunk = tool_manager._create_stream_chunk(
                            content=current_content,
                            delta=delta.content
                        )
                        logger.debug(f"Created stream chunk with content: {current_content}, delta: {delta.content}")
                        yield chunk
                        continue
                    
                    # Обрабатываем tool calls если есть
                    if delta.tool_calls and len(delta.tool_calls) > 0:
                        chunk_tool_call = delta.tool_calls[0]
                        logger.debug(f"Processing tool call: {chunk_tool_call}")
                        
                        # Создаем новый builder если нужно
                        if current_tool_builder is None:
                            current_tool_builder = ToolCallBuilder()
                        
                        # Добавляем информацию из чанка
                        current_tool_builder.add_chunk(chunk_tool_call)
                        
                        # Если tool call готов - обрабатываем
                        if current_tool_builder.can_build():
                            tool_call = current_tool_builder.build()
                            result = await tool_manager.handle_stream_chunk(
                                tool_call,
                                messages=request_params["messages"]
                            )
                            
                            if result:
                                # Создаем чанк с информацией о вызове и результате
                                chunk = tool_manager._create_stream_chunk(
                                    content=current_content,
                                    delta=""
                                )
                                # Добавляем информацию о вызове и результате
                                chunk.add_tool_call(
                                    tool_name=tool_call["function"]["name"],
                                    args=json.loads(tool_call["function"]["arguments"]),
                                    result=result["result"]["content"],
                                    tool_id=tool_call["id"]
                                )
                                yield chunk
                                
                                # Создаем новый стрим с обновленной историей
                                request_params["messages"] = result["updated_messages"]
                                current_tool_builder = None
                                break
                                
                        continue
                    
                    # Если пустой чанк и нет незавершенного tool call - отправляем финальный чанк
                    if not current_tool_builder and current_content:
                        yield tool_manager._create_stream_chunk(
                            content=current_content,
                            is_complete=True
                        )
                        return
                        
                # Если вышли из цикла по чанкам, но есть незавершенный tool call - продолжаем
                if current_tool_builder:
                    continue
                    
            logger.debug("Stream generation completed")
            
            # Отправляем финальный чанк если есть контент
            if current_content:
                yield tool_manager._create_stream_chunk(
                    content=current_content,
                    is_complete=True
                )
            
        except Exception as e:
            logger.error(f"Error generating stream response: {e}", exc_info=True)
            yield tool_manager._create_stream_chunk(
                content=f"Error: {str(e)}",
                is_complete=True
            )
