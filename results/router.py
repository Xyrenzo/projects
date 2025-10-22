from fastapi import APIRouter, Request, Depends
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from auth.dependencies import get_current_user
from results.service import ResultsService
from database.repositories import UserRepository, SessionRepository
from config import TEMPLATES_DIR

router = APIRouter(tags=["results"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

@router.get('/results', response_class=HTMLResponse)
def results_page(request: Request, user_check = Depends(get_current_user)):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    return templates.TemplateResponse("results.html", {
        "request": request,
        "user_id": user_id
    })  

@router.get('/get_user_results')
async def get_user_results(
    request: Request,
    user_check = Depends(get_current_user)
):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    
    try:
        results = ResultsService.get_user_results(user_id)
        if results:
            return results
        else:
            return {"error": "No results found"}
    except Exception as e:
        return {"error": str(e)}

@router.get('/all', response_class=HTMLResponse)
def all_types_page(request: Request, user_check = Depends(get_current_user)):
    # Проверяем, является ли результат страницей ошибки
    if not isinstance(user_check, int):
        return user_check
    
    user_id = user_check
    return templates.TemplateResponse("all.html", {
        "request": request,
        "user_id": user_id
    })

@router.get('/all/public', response_class=HTMLResponse)
def all_types_public_page(request: Request):
    return templates.TemplateResponse("all.html", {
        "request": request,
        "user_id": None
    })

@router.get('/get_users')
def get_users():
    try:
        users = UserRepository.get_all_users()
        return {"users": [{"id": u[0], "username": u[1], "email": u[2], "password": u[3]} for u in users]}
    except Exception as e:
        return {"error": str(e)}

@router.get('/get_sessions')
def get_sessions():
    try:
        sessions = SessionRepository.get_all_sessions()
        return {"sessions": [{"id": s[0], "user_id": s[1], "ip_address": s[2], "created_at": s[3]} for s in sessions]}
    except Exception as e:
        return {"error": str(e)}