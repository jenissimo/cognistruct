from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class Message(BaseModel):
    """Сообщение в чате"""
    content: str = Field(..., description="Текст сообщения")
    role: str = Field(..., description="Роль отправителя (user/assistant)")
    
class Response(BaseModel):
    """Ответ от API"""
    content: str = Field(..., description="Текст ответа")
    
class Token(BaseModel):
    """JWT токен"""
    access_token: str = Field(..., description="JWT токен доступа")
    token_type: str = Field("bearer", description="Тип токена")
    
class User(BaseModel):
    """Пользователь"""
    username: str = Field(..., description="Имя пользователя")
    scopes: List[str] = Field(default_factory=list, description="Права доступа")

class TokenData(BaseModel):
    """Данные JWT токена"""
    username: str
    scopes: List[str] = Field(
        default_factory=list,
        description="Список разрешений пользователя"
    )

class ChatRequest(BaseModel):
    """Запрос к чату с агентом"""
    message: str = Field(
        ...,
        description="Сообщение для агента",
        example="Привет! Как дела?"
    )
    system_prompt: Optional[str] = Field(
        None,
        description="Системный промпт для настройки поведения агента",
        example="Ты - дружелюбный ассистент. Отвечай кратко и по делу."
    )

class CRUDSRequest(BaseModel):
    """Запрос к CRUDS методам"""
    data: Dict[str, Any] = Field(
        ...,
        description="Данные для создания или обновления",
        example={"title": "Заметка", "content": "Текст заметки"}
    )
    query: Optional[Dict[str, Any]] = Field(
        None,
        description="Параметры поиска",
        example={"tags": ["important"]}
    )
    id: Optional[str] = Field(
        None,
        description="Идентификатор ресурса",
        example="note_123"
    )

class APIResponse(BaseModel):
    """Ответ API"""
    status: str = Field(
        default="success",
        description="Статус ответа: success или error"
    )
    data: Optional[Any] = Field(
        None,
        description="Данные ответа"
    )
    error: Optional[str] = Field(
        None,
        description="Сообщение об ошибке"
    ) 