from fastapi import FastAPI, Request, Form, HTTPException, Depends
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
import matplotlib.pyplot as plt
import io
from pathlib import Path
import sqlite3
import base64
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "users.db"

app = FastAPI()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))

# Монтируем статические файлы
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")

# Создание таблиц
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        
        # Таблица пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT NOT NULL,
                email TEXT NOT NULL UNIQUE,
                password TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Таблица ответов на опрос
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_answers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                answers TEXT NOT NULL,
                results_json TEXT NOT NULL,
                completed_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        # Таблица сессий (айпи + user_id)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_sessions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                ip_address TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')
        
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS quiz_progress (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                current_question INTEGER DEFAULT 0,
                answers_json TEXT NOT NULL,
                results_json TEXT,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id),
                UNIQUE(user_id)
            )
        ''')
        
        conn.commit()

init_db()

# Модели
class QuizResults(BaseModel):
    A: int
    B: int
    C: int
    D: int

class UserSession(BaseModel):
    user_id: int
    ip_address: str

# Вспомогательные функции
def get_client_ip(request: Request):
    return request.client.host

def verify_user_access(user_id: int, ip_address: str):
    """Проверяет, имеет ли пользователь доступ к данным"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM user_sessions WHERE user_id = ? AND ip_address = ?",
            (user_id, ip_address)
        )
        return cursor.fetchone() is not None

def create_user_session(user_id: int, ip_address: str):
    """Создает сессию для пользователя"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        # Удаляем старые сессии для этого IP
        cursor.execute(
            "DELETE FROM user_sessions WHERE ip_address = ?",
            (ip_address,)
        )
        # Создаем новую сессию
        cursor.execute(
            "INSERT INTO user_sessions (user_id, ip_address) VALUES (?, ?)",
            (user_id, ip_address)
        )
        conn.commit()

def save_user_answers(user_id: int, answers: str, results: dict):
    """Сохраняет ответы пользователя"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO user_answers (user_id, answers, results_json) VALUES (?, ?, ?)",
            (user_id, answers, str(results))
        )
        conn.commit()

def get_user_answers(user_id: int):
    """Получает сохраненные ответы пользователя"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT answers, results_json FROM user_answers WHERE user_id = ? ORDER BY completed_at DESC LIMIT 1",
            (user_id,)
        )
        result = cursor.fetchone()
        if result:
            return result[0], eval(result[1])  # answers, results
        return None, None

# Зависимости для проверки доступа
async def get_current_user(request: Request, user_id: Optional[int] = None):
    ip_address = get_client_ip(request)
    
    if user_id is None:
        # Получаем user_id из query параметров
        user_id = request.query_params.get('user_id')
        if not user_id:
            raise HTTPException(status_code=403, detail="User ID required")
        user_id = int(user_id)
    
    if not verify_user_access(user_id, ip_address):
        raise HTTPException(status_code=403, detail="Access denied")
    
    return user_id

def save_quiz_progress(user_id: int, current_question: int, answers: dict, results: dict = None):
    """Сохраняет прогресс теста"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            INSERT OR REPLACE INTO quiz_progress 
            (user_id, current_question, answers_json, results_json, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
        ''', (user_id, current_question, str(answers), str(results) if results else None))
        conn.commit()

def get_quiz_progress(user_id: int):
    """Получает прогресс теста"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            SELECT current_question, answers_json, results_json 
            FROM quiz_progress WHERE user_id = ?
        ''', (user_id,))
        result = cursor.fetchone()
        if result:
            return {
                'current_question': result[0],
                'answers': eval(result[1]) if result[1] else {},
                'results': eval(result[2]) if result[2] else None
            }
        return None

def clear_quiz_progress(user_id: int):
    """Очищает прогресс теста после завершения"""
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('DELETE FROM quiz_progress WHERE user_id = ?', (user_id,))
        conn.commit()

# Маршруты
@app.get('/')
def root(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.post('/register')
def register(
    request: Request,
    username: str = Form(...),
    email: str = Form(...),
    password: str = Form(...)
):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, email, password) VALUES (?, ?, ?)",
                (username, email, password)
            )
            user_id = cursor.lastrowid
            conn.commit()
        
        # Создаем сессию
        ip_address = get_client_ip(request)
        create_user_session(user_id, ip_address)
        
        return RedirectResponse(url=f"/questions?user_id={user_id}", status_code=303)
    except sqlite3.IntegrityError:
        return {"error": "User with this email already exists."}
    except Exception as e:
        return {"error": str(e)}

@app.post('/login')
def login(
    request: Request,
    email: str = Form(...),
    password: str = Form(...)
):
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, username, email FROM users WHERE email = ? AND password = ?",
                (email, password)
            )
            user = cursor.fetchone()
        
        if user:
            user_id = user[0]
            # Создаем сессию
            ip_address = get_client_ip(request)
            create_user_session(user_id, ip_address)
            
            return RedirectResponse(url=f"/questions?user_id={user_id}", status_code=303)
        else:
            return {"error": "Invalid email or password."}
    except Exception as e:
        return {"error": str(e)}

@app.get('/login', response_class=HTMLResponse)
def login_page(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@app.get('/register', response_class=HTMLResponse)
def register_page(request: Request):
    return templates.TemplateResponse("register.html", {"request": request})

@app.get('/questions', response_class=HTMLResponse)
def questions_page(request: Request, user_id: int = Depends(get_current_user)):
    # Получаем сохраненный прогресс из БД
    progress = get_quiz_progress(user_id)
    
    saved_answers = {}
    current_question = 0
    saved_results = None
    
    if progress:
        current_question = progress['current_question']
        saved_answers = progress['answers']
        saved_results = progress['results']
    
    return templates.TemplateResponse("questions.html", {
        "request": request,
        "user_id": user_id,
        "saved_answers": saved_answers,
        "saved_results": saved_results,
        "current_question": current_question
    })

@app.post('/process_results')
async def process_results(
    request: Request,
    user_id: int = Depends(get_current_user)
):
    try:
        # Получаем данные из тела запроса
        body = await request.json()
        print(f"Received data for user {user_id}: {body}")
        
        # Создаем объект QuizResults из полученных данных
        results = QuizResults(
            A=body.get('A', 0),
            B=body.get('B', 0),
            C=body.get('C', 0),
            D=body.get('D', 0)
        )
        
        print(f"Processing results: A={results.A}, B={results.B}, C={results.C}, D={results.D}")
        
        # Сохраняем ответы
        answers_string = f"A:{results.A},B:{results.B},C:{results.C},D:{results.D}"
        save_user_answers(user_id, answers_string, results.dict())
        
        # Очищаем прогресс теста
        clear_quiz_progress(user_id)
        
        return {"status": "success", "results": results.dict()}
        
    except Exception as e:
        print(f"Error processing results: {e}")
        return {"status": "error", "error": str(e)}
# Страницы профессий с проверкой доступа
@app.get('/A', response_class=HTMLResponse)
def type_a_page(request: Request, user_id: int = Depends(get_current_user)):
    return templates.TemplateResponse("A.html", {
        "request": request,
        "user_id": user_id
    })

@app.get('/B', response_class=HTMLResponse)
def type_b_page(request: Request, user_id: int = Depends(get_current_user)):
    return templates.TemplateResponse("B.html", {
        "request": request,
        "user_id": user_id
    })

@app.get('/C', response_class=HTMLResponse)
def type_c_page(request: Request, user_id: int = Depends(get_current_user)):
    return templates.TemplateResponse("C.html", {
        "request": request,
        "user_id": user_id
    })

@app.get('/D', response_class=HTMLResponse)
def type_d_page(request: Request, user_id: int = Depends(get_current_user)):
    return templates.TemplateResponse("D.html", {
        "request": request,
        "user_id": user_id
    })

# API для получения пользователей (для отладки)
@app.get('/get_users')
def get_users():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, username, email, password FROM users")
            users = cursor.fetchall()
        return {"users": [{"id": u[0], "username": u[1], "email": u[2], "password": u[3]} for u in users]}
    except Exception as e:
        return {"error": str(e)}

@app.get('/get_sessions')
def get_sessions():
    try:
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT id, user_id, ip_address, created_at FROM user_sessions")
            sessions = cursor.fetchall()
        return {"sessions": [{"id": s[0], "user_id": s[1], "ip_address": s[2], "created_at": s[3]} for s in sessions]}
    except Exception as e:
        return {"error": str(e)}

@app.post('/save_quiz_progress')
async def save_quiz_progress_endpoint(
    request: Request,
    user_id: int = Depends(get_current_user)
):
    try:
        body = await request.json()
        save_quiz_progress(
            user_id=user_id,
            current_question=body.get('current_question', 0),
            answers=body.get('answers', {}),
            results=body.get('results')
        )
        return {"status": "success"}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@app.get('/get_quiz_progress')
async def get_quiz_progress_endpoint(
    request: Request,
    user_id: int = Depends(get_current_user)
):
    try:
        progress = get_quiz_progress(user_id)
        return progress or {}
    except Exception as e:
        return {"error": str(e)}
    
@app.get('/results', response_class=HTMLResponse)
def results_page(request: Request, user_id: int = Depends(get_current_user)):
    return templates.TemplateResponse("results.html", {
        "request": request,
        "user_id": user_id
    })

@app.get('/get_user_results')
async def get_user_results(
    request: Request,
    user_id: int = Depends(get_current_user)
):
    try:
        # Получаем последние результаты пользователя
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT results_json FROM user_answers 
                WHERE user_id = ? 
                ORDER BY completed_at DESC 
                LIMIT 1
            ''', (user_id,))
            result = cursor.fetchone()
            
            if result and result[0]:
                results_data = eval(result[0])
                
                # Генерируем график заново для результатов
                plt.style.use('default')
                fig, ax = plt.subplots(figsize=(10, 6))
                
                types = ['A', 'B', 'C', 'D']
                counts = [results_data.get('A', 0), results_data.get('B', 0), 
                         results_data.get('C', 0), results_data.get('D', 0)]
                colors = ['#FF6B6B', '#4ECDC4', '#45B7D1', '#96CEB4']
                
                bars = ax.bar(types, counts, color=colors, edgecolor='black', linewidth=2, alpha=0.8)
                
                for bar, count in zip(bars, counts):
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                            f'{count}', ha='center', va='bottom', fontsize=14, fontweight='bold')
                
                ax.set_ylabel('Количество ответов', fontsize=12, fontweight='bold')
                ax.set_xlabel('Типы личности', fontsize=12, fontweight='bold')
                ax.set_title('Результаты опросника', fontsize=16, fontweight='bold', pad=20)
                ax.set_ylim(0, max(counts) + 2)
                
                ax.grid(axis='y', alpha=0.3, linestyle='--')
                ax.set_axisbelow(True)
                
                for spine in ax.spines.values():
                    spine.set_visible(False)
                
                buf = io.BytesIO()
                plt.savefig(buf, format='png', dpi=100, bbox_inches='tight', 
                           facecolor='white', edgecolor='none')
                plt.close(fig)
                buf.seek(0)
                
                image_base64 = base64.b64encode(buf.getvalue()).decode('utf-8')
                
                return {
                    "results": results_data,
                    "image": f"data:image/png;base64,{image_base64}"
                }
            else:
                return {"error": "No results found"}
    except Exception as e:
        return {"error": str(e)}