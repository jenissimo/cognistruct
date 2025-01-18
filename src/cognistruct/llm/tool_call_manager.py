"""Менеджер для работы с вызовами инструментов и их результатами"""

import json
from typing import Dict, Any, List, Optional, Set, Callable, Awaitable, Union, AsyncGenerator, TypedDict
from dataclasses import dataclass
import uuid

from openai.types.chat import ChatCompletionMessageToolCall
from openai.types.chat.chat_completion_chunk import ChoiceDeltaToolCall

from cognistruct.core.messages import IOMessage
from cognistruct.llm.interfaces import ToolCall
from cognistruct.utils.logging import setup_logger

logger = setup_logger(__name__)


class ToolCallDict(TypedDict):
    """Структура tool call в виде словаря"""
    id: str
    type: str
    function: Dict[str, str]


@dataclass
class ToolCallResult:
    """Результат выполнения инструмента"""
    call: ToolCallDict  # Информация о вызове
    result: Dict[str, Any]  # Результат выполнения
    error: Optional[str] = None  # Ошибка если была


class ToolCallBuilder:
    """Класс для сборки tool call из чанков"""
    
    def __init__(self):
        self.id: Optional[str] = None
        self.name: Optional[str] = None
        self._arguments: List[str] = []
        
    @staticmethod
    def create(tool_call: ChatCompletionMessageToolCall) -> 'ToolCallBuilder':
        """
        Создает готовый билдер из ChatCompletionMessageToolCall
        
        Args:
            tool_call: Готовый tool call от OpenAI API
            
        Returns:
            ToolCallBuilder: Готовый к использованию билдер
        """
        builder = ToolCallBuilder()
        # Проверяем, является ли tool_call словарем или объектом
        if isinstance(tool_call, dict):
            builder.id = tool_call.get('id')
            builder.name = tool_call.get('function', {}).get('name')
            builder._arguments = [tool_call.get('function', {}).get('arguments', '')]
        else:
            builder.id = tool_call.id
            builder.name = tool_call.function.name
            builder._arguments = [tool_call.function.arguments]
        return builder
        
    def add_chunk(self, chunk_tool_call: Union[ChoiceDeltaToolCall, ChatCompletionMessageToolCall]) -> None:
        """Добавляет информацию из чанка"""
        # Обновляем ID если пришел
        if hasattr(chunk_tool_call, 'id') and chunk_tool_call.id:
            self.id = chunk_tool_call.id
            
        # Обновляем имя если пришло
        if (hasattr(chunk_tool_call, 'function') and 
            hasattr(chunk_tool_call.function, 'name') and 
            chunk_tool_call.function.name):
            self.name = chunk_tool_call.function.name
            
        # Добавляем аргументы если пришли
        if (hasattr(chunk_tool_call, 'function') and 
            hasattr(chunk_tool_call.function, 'arguments') and 
            chunk_tool_call.function.arguments):
            self._arguments.append(chunk_tool_call.function.arguments)
    
    @property        
    def arguments(self) -> str:
        """Возвращает собранные аргументы"""
        return "".join(self._arguments)
    
    def can_build(self) -> bool:
        """Проверяет, можно ли построить полный tool call"""
        if not (self.id and self.name and self.arguments):
            return False
            
        args = self.arguments
        if not (args.startswith("{") and args.endswith("}")):
            return False
            
        try:
            json.loads(args)
            return True
        except json.JSONDecodeError:
            return False
            
    def build(self) -> ToolCallDict:
        """Создает готовый tool call"""
        if not self.can_build():
            raise ValueError("Tool call не готов")
            
        return {
            "id": self.id,
            "type": "function",
            "function": {
                "name": self.name,
                "arguments": self.arguments
            }
        }


class ToolCallManager:
    """Менеджер для работы с вызовами инструментов и их результатами"""
    
    def __init__(self):
        self._tool_executor: Optional[Callable[[str, Dict[str, Any]], Awaitable[Any]]] = None
        self._processed_calls: Set[str] = set()  # Для отслеживания дубликатов
        
    def set_tool_executor(self, executor: Callable[[str, Dict[str, Any]], Awaitable[Any]]) -> None:
        """Устанавливает функцию для выполнения инструментов"""
        self._tool_executor = executor
        
    def _generate_tool_call_id(self) -> str:
        """Генерирует уникальный ID для вызова инструмента"""
        return f"call_{len(self._processed_calls)}_{uuid.uuid4()}"
        
    def _is_duplicate_call(self, tool_name: str, args_str: str) -> bool:
        """Проверяет, был ли такой вызов инструмента уже обработан"""
        call_hash = f"{tool_name}:{args_str}"
        if call_hash in self._processed_calls:
            return True
        self._processed_calls.add(call_hash)
        return False
        
    async def process_tool_calls(
        self,
        tool_calls: List[ToolCallDict],
        messages: List[Dict[str, Any]]
    ) -> List[ToolCallResult]:
        """
        Обрабатывает список вызовов инструментов
        
        Args:
            tool_calls: Список вызовов инструментов
            messages: История сообщений для обновления
            
        Returns:
            List[ToolCallResult]: Результаты выполнения инструментов
        """
        if not self._tool_executor:
            raise RuntimeError("Tool executor не установлен")
            
        results = []
        
        # Создаем сообщение от ассистента с вызовами инструментов
        assistant_message = {
            "role": "assistant",
            "content": None,
            "tool_calls": []
        }
        
        for tool_call in tool_calls:
            # Получаем имя и аргументы инструмента
            tool_name = tool_call['function']['name']
            tool_args = tool_call['function']['arguments']
            
            # Проверяем на дубликат
            if self._is_duplicate_call(tool_name, tool_args):
                continue
                
            try:
                # Парсим аргументы
                args = json.loads(tool_args)
                tool_id = tool_call.get('id', self._generate_tool_call_id())
                
                # Добавляем информацию о вызове в сообщение ассистента
                assistant_message["tool_calls"].append({
                    "id": tool_id,
                    "type": "function",
                    "function": {
                        "name": tool_name,
                        "arguments": tool_args
                    }
                })
                
                # Выполняем инструмент
                result = await self._tool_executor(tool_name, args)
                
                # Создаем сообщение с результатом
                tool_message = {
                    "role": "tool",
                    "content": str(result),
                    "tool_call_id": tool_id
                }
                
                # Добавляем сообщения в историю
                messages.extend([assistant_message, tool_message])
                
                # Сохраняем результат
                results.append(ToolCallResult(
                    call=tool_call,  # Используем оригинальный tool_call
                    result=tool_message,
                    error=None
                ))
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Tool execution failed: {error_msg}")
                
                # Сохраняем ошибку
                results.append(ToolCallResult(
                    call=tool_call,  # Используем оригинальный tool_call даже при ошибке
                    result=None,
                    error=error_msg
                ))
                
        return results
        
    def _create_stream_chunk(
        self, 
        content: str = "", 
        delta: str = "", 
        tool_call: Optional[ToolCallDict] = None, 
        tool_result: Optional[Dict] = None, 
        is_complete: bool = False
    ) -> IOMessage:
        """
        Создает чанк стрима
        
        Args:
            content: Текущий накопленный контент
            delta: Новый фрагмент контента
            tool_call: Информация о вызове инструмента
            tool_result: Результат выполнения инструмента
            is_complete: Флаг завершения генерации
            
        Returns:
            IOMessage: Чанк стрима
        """
        chunk = IOMessage(
            type="stream_chunk",
            content=content,
            metadata={
                "delta": delta,
                "is_complete": is_complete
            }
        )
        
        if tool_call:
            chunk.add_tool_call(
                tool_name=tool_call["function"]["name"],
                args=json.loads(tool_call["function"]["arguments"]),
                tool_id=tool_call["id"]
            )
        
        if tool_result:
            # Добавляем результат к последнему tool_call
            if chunk.tool_calls:
                last_call = chunk.get_last_tool_call()
                if last_call:
                    last_call["result"] = tool_result
        
        return chunk
        
    async def handle_stream_chunk(
        self,
        tool_call: ToolCallDict,
        messages: Optional[List[Dict[str, Any]]] = None
    ) -> Optional[Dict[str, Any]]:
        """
        Обрабатывает готовый tool call из стрима
        
        Args:
            tool_call: Готовый tool call
            messages: История сообщений для обновления
            
        Returns:
            Optional[Dict[str, Any]]: Результат обработки или None если tool call не готов
        """
        try:
            logger.debug(f"Processing tool call: {tool_call}")
            
            # Проверяем на дубликат
            args_str = tool_call["function"]["arguments"].strip()
            if self._is_duplicate_call(tool_call["function"]["name"], args_str):
                return None
                
            # Создаем сообщение от ассистента
            assistant_message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [tool_call]
            }
            
            try:
                # Выполняем инструмент
                args = json.loads(args_str)
                result = await self._tool_executor(
                    tool_call["function"]["name"],
                    args
                )
                
                # Создаем сообщение с результатом
                tool_message = {
                    "role": "tool",
                    "content": str(result),
                    "tool_call_id": tool_call["id"]
                }
                
                # Добавляем сообщения в историю если она передана
                if messages is not None:
                    messages.extend([assistant_message, tool_message])
                
                return {
                    "call": tool_call,
                    "result": {"content": str(result)},
                    "updated_messages": messages
                }
                
            except Exception as e:
                error_msg = str(e)
                logger.error(f"Tool execution failed: {error_msg}")
                
                tool_message = {
                    "role": "tool",
                    "content": str(error_msg),
                    "tool_call_id": tool_call["id"]
                }
                
                # Добавляем сообщения в историю если она передана
                if messages is not None:
                    messages.extend([assistant_message, tool_message])
                
                return {
                    "call": tool_call,
                    "result": {"content": f"Error: {error_msg}"},
                    "updated_messages": messages
                }
                
        except Exception as e:
            logger.error(f"Error processing stream chunk: {e}", exc_info=True)
            return None 