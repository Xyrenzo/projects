from fastapi import APIRouter, Request, Form, HTTPException
from fastapi.responses import RedirectResponse, HTMLResponse
from fastapi.templating import Jinja2Templates
from auth.service import AuthService
from auth.dependencies import get_client_ip
from config import TEMPLATES_DIR
import sqlite3

router = APIRouter(tags=["auth"])
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# маршрутизация клиента в регистрационную страницу или в страницу логина

@router.get('/')
def root(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@router.post('/register')
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    try:
        ip_address = get_client_ip(request)
        user_id = AuthService.register_user(username, email, password, ip_address)
        # Store user ID in session cookie
        response = RedirectResponse(url=f"/questions?user_id={user_id}", status_code=303)
        response.set_cookie(key="user_id", value=str(user_id), httponly=True)
        return response
    except sqlite3.IntegrityError as e:
        if "UNIQUE constraint failed: users.email" in str(e):
            # Email уже существует в базе данных
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error_message": "Пользователь с таким email уже существует. Пожалуйста, используйте другой email или войдите в существующий аккаунт."
            })
        else:
            return templates.TemplateResponse("register.html", {
                "request": request,
                "error_message": "Произошла ошибка при регистрации. Пожалуйста, попробуйте еще раз."
            })
    except Exception as e:
        return templates.TemplateResponse("register.html", {
            "request": request,
            "error_message": f"Произошла ошибка: {str(e)}"
        })

@router.post('/login')
def login(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    try:
        ip_address = get_client_ip(request)
        # First try to find user by username and email
        user = UserRepository.get_user_by_username_and_email(username, email)
        if user and user[3] == password:  # Check password (index 3 is password)
            user_id = user[0]
            SessionRepository.create_session(user_id, ip_address)
            # Store user ID in session cookie
            response = RedirectResponse(url=f"/questions?user_id={user_id}", status_code=303)
            response.set_cookie(key="user_id", value=str(user_id), httponly=True)
            return response
        else:
            return templates.TemplateResponse("login.html", {
                "request": request,
                "error_message": "Неверный никнейм, email или пароль. Пожалуйста, попробуйте еще раз."
            })
    except Exception as e:
        return templates.TemplateResponse("login.html", {
            "request": request,
            "error_message": f"Произошла ошибка при входе: {str(e)}"
        })

@router.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.get('/register', response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

# Import at the end to avoid circular imports
from database.repositories import UserRepository, SessionRepository