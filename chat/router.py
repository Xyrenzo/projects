from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from auth.dependencies import get_current_user
from chat.bot import CareerGuideBot
from chat.models import ChatMessage, CreateChatRequest, RenameChatRequest
from config import TEMPLATES_DIR

router = APIRouter(prefix = "/chat",tags=["chat_bot"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
chat_bot = CareerGuideBot()

@router.get('/', response_class=HTMLResponse)
def chat_bot_page(request: Request, user_check = Depends(get_current_user)):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    return templates.TemplateResponse("chat_bot.html", {
        "request": request,
        "user_id": user_id
    })

@router.get('/chats')
async def get_user_chats(
    request: Request,
    user_check = Depends(get_current_user)
):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    
    try:
        chats = chat_bot.get_chats(user_id)
        active_chat = chat_bot.get_active_chat(user_id)
        return {
            "status": "success",
            "chats": chats,
            "active_chat": active_chat
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.post('/create')
async def create_chat(
    request: Request,
    create_request: CreateChatRequest,
    user_check = Depends(get_current_user)
):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    
    try:
        chat_id = chat_bot.create_chat(user_id, create_request.title)
        return {
            "status": "success",
            "chat_id": chat_id
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.post('/{chat_id}/set_active')
async def set_active_chat(
    request: Request,
    chat_id: int,
    user_check = Depends(get_current_user)
):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    
    try:
        success = chat_bot.set_active_chat(user_id, chat_id)
        if success:
            return {"status": "success"}
        else:
            return {"status": "error", "error": "Chat not found"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.delete('/{chat_id}')
async def delete_chat(
    request: Request,
    chat_id: int,
    user_check = Depends(get_current_user)
):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    
    try:
        success = chat_bot.delete_chat(user_id, chat_id)
        if success:
            return {"status": "success"}
        else:
            return {"status": "error", "error": "Chat not found"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.put('/{chat_id}/rename')
async def rename_chat(
    request: Request,
    chat_id: int,
    rename_request: RenameChatRequest,
    user_check = Depends(get_current_user)
):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    
    try:
        success = chat_bot.rename_chat(user_id, chat_id, rename_request.title)
        if success:
            return {"status": "success"}
        else:
            return {"status": "error", "error": "Chat not found"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.get('/messages')
async def get_chat_messages(
    request: Request,
    user_check = Depends(get_current_user)
):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    
    try:
        active_chat = chat_bot.get_active_chat(user_id)
        if not active_chat:
            return {"status": "success", "messages": []}

        messages = chat_bot.get_messages(active_chat["id"])
        return {
            "status": "success",
            "messages": messages,
            "active_chat": active_chat
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.post('/send')
async def send_message(
    request: Request,
    chat_message: ChatMessage,
    user_check = Depends(get_current_user)
):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    
    try:
        response = chat_bot.get_response(user_id, chat_message.message)
        return {
            "status": "success",
            "response": response
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.get('/profile')
async def get_user_profile(
    request: Request,
    user_check = Depends(get_current_user)
):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    
    try:
        # Импортируем UserRepository
        from database.repositories import UserRepository
        profile = UserRepository.get_user_profile(user_id)
        return {
            "status": "success",
            "profile": profile if profile else {}
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}

@router.put('/profile')
async def update_user_profile(
    request: Request,
    profile_data: dict,
    user_check = Depends(get_current_user)
):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    
    try:
        # Импортируем UserRepository
        from database.repositories import UserRepository
        success = UserRepository.update_user_profile(user_id, profile_data)
        if success:
            return {"status": "success"}
        else:
            return {"status": "error", "error": "Failed to update profile"}
    except Exception as e:
        return {"status": "error", "error": str(e)}