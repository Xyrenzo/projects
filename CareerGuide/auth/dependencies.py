from fastapi import Request, HTTPException, Depends
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, HTMLResponse
from database.repositories import SessionRepository, UserRepository
from config import TEMPLATES_DIR
import hashlib
from typing import Union

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

def get_client_ip(request: Request) -> str:
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0]
    if request.client:
        return request.client.host
    return "unknown"

def get_current_user(request: Request):
    # Получаем user_id из query параметров
    user_id = request.query_params.get("user_id")
    
    # Also check in cookies as fallback
    if not user_id:
        user_id = request.cookies.get("user_id")
    
    if not user_id:
        # Если user_id нет в параметрах, показываем страницу ошибки
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "Для доступа к этой странице необходимо войти в аккаунт или зарегистрироваться."
        })
    
    try:
        user_id = int(user_id)
    except ValueError:
        # Если user_id не число, показываем страницу ошибки
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "Неверный формат идентификатора пользователя."
        })
    
    # Проверяем, существует ли пользователь
    user = UserRepository.get_user_by_id(user_id)
    if not user:
        # Если пользователь не найден, показываем страницу ошибки
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "Пользователь не найден. Возможно, ваша сессия истекла."
        })
    
    # Проверяем сессию пользователя
    session = SessionRepository.get_session_by_user_id(user_id)
    if not session:
        # Если сессия не найдена, показываем страницу ошибки
        return templates.TemplateResponse("error.html", {
            "request": request,
            "error_message": "Сессия не найдена. Пожалуйста, войдите снова."
        })
    
    # Проверяем IP адрес сессии - если не совпадает, создаем новую сессию
    client_ip = get_client_ip(request)
    if session[2] != client_ip:
        # Если IP не совпадает, создаем новую сессию вместо отказа в доступе
        SessionRepository.create_session(user_id, client_ip)
    
    return user_id