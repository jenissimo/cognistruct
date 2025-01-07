import os
import jwt
import asyncio
import logging
from datetime import datetime, timedelta
from typing import Optional, Dict, Any, List
from functools import wraps

from fastapi import FastAPI, HTTPException, Depends, Security, Body
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from pydantic import BaseModel, Field
import uvicorn

from plugins.base_plugin import BasePlugin, IOMessage

logger = logging.getLogger(__name__)

# Модели данных
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

class RESTApiPlugin(BasePlugin):
    """REST API плагин с автоматической генерацией CRUDS эндпоинтов"""

    def __init__(
        self,
        host: str = "0.0.0.0",
        port: int = 8000,
        jwt_secret: Optional[str] = None,
        jwt_algorithm: str = "HS256",
        token_expire_minutes: int = 30,
        enable_auth: bool = False,
        allowed_origins: List[str] = None,
        admin_username: Optional[str] = None,
        admin_password: Optional[str] = None
    ):
        super().__init__()
        self.host = host
        self.port = port
        self.jwt_secret = jwt_secret or os.urandom(32).hex()
        self.jwt_algorithm = jwt_algorithm
        self.token_expire_minutes = token_expire_minutes
        self.enable_auth = enable_auth or bool(admin_username and admin_password)
        self.allowed_origins = allowed_origins or ["*"]
        self.admin_username = admin_username
        self.admin_password = admin_password
        
        # Создаем FastAPI приложение
        self.app = FastAPI(
            title="CogniStruct API",
            description="""
            REST API для доступа к плагинам и чату с агентом.
            
            ## Возможности
            
            ### 🔐 Авторизация
            - Получение JWT токена через `/auth/token`
            - Защита эндпоинтов через Bearer Authentication
            
            ### 💬 Чат с агентом
            - Отправка сообщений через `/chat`
            - Поддержка системных промптов
            
            ### 📦 CRUDS API для плагинов
            Для каждого плагина с поддержкой CRUDS автоматически создаются эндпоинты:
            - `POST /api/{plugin}` - создание
            - `GET /api/{plugin}/{id}` - чтение
            - `PUT /api/{plugin}/{id}` - обновление
            - `DELETE /api/{plugin}/{id}` - удаление
            - `POST /api/{plugin}/search` - поиск
            
            ## Примеры использования
            
            ### Получение токена
            ```bash
            curl -X POST "http://localhost:8000/auth/token" \\
                 -d "username=admin&password=secret"
            ```
            
            ### Чат с агентом
            ```bash
            curl -X POST "http://localhost:8000/chat" \\
                 -H "Authorization: Bearer YOUR_TOKEN" \\
                 -H "Content-Type: application/json" \\
                 -d '{"message": "Привет!", "system_prompt": "Будь дружелюбным"}'
            ```
            
            ### Работа с хранилищем
            ```bash
            # Создание заметки
            curl -X POST "http://localhost:8000/api/storage" \\
                 -H "Authorization: Bearer YOUR_TOKEN" \\
                 -H "Content-Type: application/json" \\
                 -d '{"data": {"title": "Заметка", "content": "Текст"}}'
                 
            # Поиск заметок
            curl -X POST "http://localhost:8000/api/storage/search" \\
                 -H "Authorization: Bearer YOUR_TOKEN" \\
                 -H "Content-Type: application/json" \\
                 -d '{"query": {"tags": ["important"]}}'
            ```
            """,
            version="1.0.0",
            docs_url="/docs",
            redoc_url="/redoc"
        )
        
        # Добавляем CORS
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=self.allowed_origins,
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )
        
        # Схема авторизации
        self.security = HTTPBearer()
        
        # Регистрируем базовые роуты
        self._setup_routes()
        
        # Кастомизируем OpenAPI схему
        def custom_openapi():
            if self.app.openapi_schema:
                return self.app.openapi_schema
                
            openapi_schema = get_openapi(
                title=self.app.title,
                version=self.app.version,
                description=self.app.description,
                routes=self.app.routes
            )
            
            # Добавляем Bearer Auth
            openapi_schema["components"]["securitySchemes"] = {
                "Bearer": {
                    "type": "http",
                    "scheme": "bearer",
                    "bearerFormat": "JWT"
                }
            }
            
            self.app.openapi_schema = openapi_schema
            return self.app.openapi_schema
            
        self.app.openapi = custom_openapi
        
    async def setup(self):
        """Инициализация плагина"""
        # Запускаем сервер в отдельном таске
        asyncio.create_task(self._run_server())
        
    async def cleanup(self):
        """Очистка ресурсов"""
        # TODO: Graceful shutdown
        pass
        
    def _setup_routes(self):
        """Настройка базовых роутов"""
        
        # Аутентификация
        @self.app.post(
            "/auth/token",
            response_model=APIResponse,
            tags=["auth"],
            summary="Получение JWT токена",
            description="""
            Аутентификация пользователя и получение JWT токена.
            Токен необходим для доступа к защищенным эндпоинтам.
            """
        )
        async def login(
            username: str = Body(..., example="admin"),
            password: str = Body(..., example="secret")
        ):
            if not self.enable_auth:
                raise HTTPException(400, "Authentication is disabled")
                
            if not self.admin_username or not self.admin_password:
                raise HTTPException(500, "Admin credentials not configured")
                
            if username == self.admin_username and password == self.admin_password:
                token = self._create_token({
                    "username": username,
                    "scopes": ["admin"]
                })
                return APIResponse(data={"access_token": token})
            raise HTTPException(401, "Invalid credentials")
            
        # Чат с агентом
        @self.app.post(
            "/chat",
            response_model=APIResponse,
            tags=["chat"],
            summary="Отправка сообщения агенту",
            description="""
            Отправка сообщения агенту и получение ответа.
            Можно указать системный промпт для настройки поведения.
            """
        )
        async def chat(
            request: ChatRequest,
            token: Optional[HTTPAuthorizationCredentials] = Security(self.security) if self.enable_auth else None
        ):
            if self.enable_auth:
                await self._verify_token(token)
                
            try:
                response = await self.agent.process_message(
                    message=request.message,
                    system_prompt=request.system_prompt
                )
                return APIResponse(data={"response": response})
            except Exception as e:
                logger.exception("Error processing chat request")
                raise HTTPException(500, str(e))
                
    async def _register_plugin_routes(self, plugin_name: str, plugin: BasePlugin):
        """Регистрация CRUDS роутов для плагина"""
        
        # Проверяем наличие CRUDS методов
        has_cruds = all(
            hasattr(plugin, method) 
            for method in ['create', 'read', 'update', 'delete', 'search']
        )
        
        if not has_cruds:
            return
            
        # Create
        @self.app.post(
            f"/api/{plugin_name}",
            response_model=APIResponse,
            tags=[plugin_name],
            summary=f"Создание ресурса в {plugin_name}",
            description=f"Создание нового ресурса через плагин {plugin_name}"
        )
        async def create(
            request: CRUDSRequest,
            token: Optional[HTTPAuthorizationCredentials] = Security(self.security) if self.enable_auth else None
        ):
            if self.enable_auth:
                await self._verify_token(token)
            result = await plugin.create(request.data)
            return APIResponse(data=result)
            
        # Read
        @self.app.get(
            f"/api/{plugin_name}/{{id}}",
            response_model=APIResponse,
            tags=[plugin_name],
            summary=f"Получение ресурса из {plugin_name}",
            description=f"Получение ресурса по ID через плагин {plugin_name}"
        )
        async def read(
            id: str,
            token: Optional[HTTPAuthorizationCredentials] = Security(self.security) if self.enable_auth else None
        ):
            if self.enable_auth:
                await self._verify_token(token)
            result = await plugin.read(id)
            if result is None:
                raise HTTPException(404, "Not found")
            return APIResponse(data=result)
            
        # Update
        @self.app.put(
            f"/api/{plugin_name}/{{id}}",
            response_model=APIResponse,
            tags=[plugin_name],
            summary=f"Обновление ресурса в {plugin_name}",
            description=f"Обновление существующего ресурса через плагин {plugin_name}"
        )
        async def update(
            id: str,
            request: CRUDSRequest,
            token: Optional[HTTPAuthorizationCredentials] = Security(self.security) if self.enable_auth else None
        ):
            if self.enable_auth:
                await self._verify_token(token)
            result = await plugin.update(id, request.data)
            if not result:
                raise HTTPException(404, "Not found")
            return APIResponse(data={"success": True})
            
        # Delete
        @self.app.delete(
            f"/api/{plugin_name}/{{id}}",
            response_model=APIResponse,
            tags=[plugin_name],
            summary=f"Удаление ресурса из {plugin_name}",
            description=f"Удаление ресурса по ID через плагин {plugin_name}"
        )
        async def delete(
            id: str,
            token: Optional[HTTPAuthorizationCredentials] = Security(self.security) if self.enable_auth else None
        ):
            if self.enable_auth:
                await self._verify_token(token)
            result = await plugin.delete(id)
            if not result:
                raise HTTPException(404, "Not found")
            return APIResponse(data={"success": True})
            
        # Search
        @self.app.post(
            f"/api/{plugin_name}/search",
            response_model=APIResponse,
            tags=[plugin_name],
            summary=f"Поиск ресурсов в {plugin_name}",
            description=f"Поиск ресурсов по параметрам через плагин {plugin_name}"
        )
        async def search(
            request: CRUDSRequest,
            token: Optional[HTTPAuthorizationCredentials] = Security(self.security) if self.enable_auth else None
        ):
            if self.enable_auth:
                await self._verify_token(token)
            result = await plugin.search(request.query or {})
            return APIResponse(data=result)
            
    def _create_token(self, data: dict) -> str:
        """Создает JWT токен"""
        expires = datetime.utcnow() + timedelta(minutes=self.token_expire_minutes)
        to_encode = data.copy()
        to_encode.update({"exp": expires})
        return jwt.encode(to_encode, self.jwt_secret, algorithm=self.jwt_algorithm)
        
    async def _verify_token(self, credentials: HTTPAuthorizationCredentials) -> TokenData:
        """Проверяет JWT токен"""
        try:
            payload = jwt.decode(
                credentials.credentials,
                self.jwt_secret,
                algorithms=[self.jwt_algorithm]
            )
            username: str = payload.get("username")
            if username is None:
                raise HTTPException(401, "Invalid token")
            return TokenData(username=username)
        except jwt.ExpiredSignatureError:
            raise HTTPException(401, "Token expired")
        except jwt.JWTError:
            raise HTTPException(401, "Invalid token")
            
    async def _run_server(self):
        """Запускает FastAPI сервер"""
        config = uvicorn.Config(
            self.app,
            host=self.host,
            port=self.port,
            log_level="info"
        )
        server = uvicorn.Server(config)
        await server.serve()
        
    async def on_plugin_registered(self, plugin_name: str, plugin: BasePlugin):
        """Хук вызывается при регистрации нового плагина"""
        await self._register_plugin_routes(plugin_name, plugin) 