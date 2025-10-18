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

# пути к файлу, не нужны.
BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "users.db"

app = FastAPI()
templates = Jinja2Templates(directory=str(BASE_DIR / "templates"))


#инициализация баз данных, не нужно трогать, только если потребуется
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

        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_chats (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                title TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (user_id) REFERENCES users (id)
            )
        ''')

        # Таблица сообщений
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS chat_messages (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                role TEXT NOT NULL, -- 'user' или 'assistant'
                content TEXT NOT NULL,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                FOREIGN KEY (chat_id) REFERENCES user_chats (id)
            )
        ''')

        # Таблица активных чатов пользователей
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS user_active_chats (
                user_id INTEGER PRIMARY KEY,
                active_chat_id INTEGER,
                FOREIGN KEY (user_id) REFERENCES users (id),
                FOREIGN KEY (active_chat_id) REFERENCES user_chats (id)
            )
        ''')

        conn.commit()


init_db()



#неудачная попытка подключть ИИ, блок бесполезен
class CareerGuideBot:
    def __init__(self):
        try:
            self.tokenizer = AutoTokenizer.from_pretrained("sberbank-ai/rugpt3small_based_on_gpt2")
            self.model = AutoModelForCausalLM.from_pretrained("sberbank-ai/rugpt3small_based_on_gpt2")
            
            # Добавляем специальные токены
            self.tokenizer.add_special_tokens({
                'pad_token': '[PAD]',
                'sep_token': '[SEP]'
            })
            
            print("AI model loaded successfully: ruGPT-3 Small")
            
        except Exception as e:
            print(f"Error loading AI model: {e}")
            print("Using smart mock responses")
            self.tokenizer = None
            self.model = None

    def create_chat(self, user_id: int, title: str = "Новый чат"):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO user_chats (user_id, title) VALUES (?, ?)",
                (user_id, title)
            )
            chat_id = cursor.lastrowid
            
            # Устанавливаем как активный чат
            cursor.execute('''
                INSERT OR REPLACE INTO user_active_chats (user_id, active_chat_id)
                VALUES (?, ?)
            ''', (user_id, chat_id))
            
            conn.commit()
            return chat_id
            
    def get_chats(self, user_id: int):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT id, title, created_at, updated_at 
                FROM user_chats 
                WHERE user_id = ? 
                ORDER BY updated_at DESC
            ''', (user_id,))
            chats = cursor.fetchall()
            
            return [{
                "id": chat[0],
                "title": chat[1],
                "created_at": chat[2],
                "updated_at": chat[3]
            } for chat in chats]
            
    def set_active_chat(self, user_id: int, chat_id: int):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Проверяем, что чат принадлежит пользователю
            cursor.execute(
                "SELECT id FROM user_chats WHERE id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            if cursor.fetchone():
                cursor.execute('''
                    INSERT OR REPLACE INTO user_active_chats (user_id, active_chat_id)
                    VALUES (?, ?)
                ''', (user_id, chat_id))
                conn.commit()
                return True
            return False
            
    def get_active_chat(self, user_id: int):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT uc.id, uc.title, uc.created_at, uc.updated_at
                FROM user_chats uc
                JOIN user_active_chats uac ON uc.id = uac.active_chat_id
                WHERE uac.user_id = ?
            ''', (user_id,))
            chat = cursor.fetchone()
            
            if chat:
                return {
                    "id": chat[0],
                    "title": chat[1],
                    "created_at": chat[2],
                    "updated_at": chat[3]
                }
            return None
            
    def delete_chat(self, user_id: int, chat_id: int):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            # Проверяем принадлежность чата
            cursor.execute(
                "SELECT id FROM user_chats WHERE id = ? AND user_id = ?",
                (chat_id, user_id)
            )
            if not cursor.fetchone():
                return False
                
            # Удаляем сообщения чата
            cursor.execute("DELETE FROM chat_messages WHERE chat_id = ?", (chat_id,))
            # Удаляем чат
            cursor.execute("DELETE FROM user_chats WHERE id = ?", (chat_id,))
            
            # Если удалили активный чат, сбрасываем активный чат
            cursor.execute(
                "SELECT active_chat_id FROM user_active_chats WHERE user_id = ?",
                (user_id,)
            )
            active_chat = cursor.fetchone()
            if active_chat and active_chat[0] == chat_id:
                cursor.execute(
                    "DELETE FROM user_active_chats WHERE user_id = ?",
                    (user_id,)
                )
                
            conn.commit()
            return True
            
    def add_message(self, chat_id: int, role: str, content: str):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO chat_messages (chat_id, role, content) VALUES (?, ?, ?)",
                (chat_id, role, content)
            )
            # Обновляем время изменения чата
            cursor.execute(
                "UPDATE user_chats SET updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (chat_id,)
            )
            conn.commit()
    def get_messages(self, chat_id: int):
        with sqlite3.connect(DB_PATH) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                SELECT role, content, created_at 
                FROM chat_messages 
                WHERE chat_id = ? 
                ORDER BY created_at ASC
            ''', (chat_id,))
            messages = cursor.fetchall()
        
            return [{
                "role": msg[0],
                "content": msg[1],
                "created_at": msg[2]
            } for msg in messages]
        
    def get_response(self, user_id: int, message: str) -> str:
        if self.model is None or self.tokenizer is None:
            return self._get_smart_mock_response(message)
            
        try:
            active_chat = self.get_active_chat(user_id)
            if not active_chat:
                chat_id = self.create_chat(user_id, message[:30] + "..." if len(message) > 30 else message)
                active_chat = self.get_active_chat(user_id)
            else:
                chat_id = active_chat["id"]
                
            self.add_message(chat_id, "user", message)
            
            # Более качественный промпт
            prompt = self._build_prompt(chat_id, message)
            
            inputs = self.tokenizer.encode(prompt, return_tensors="pt", max_length=768, truncation=True)
            
            with torch.no_grad():
                outputs = self.model.generate(
                    inputs,
                    max_new_tokens=200,
                    temperature=0.8,
                    do_sample=True,
                    top_p=0.9,
                    pad_token_id=self.tokenizer.eos_token_id,
                    repetition_penalty=1.1,
                    no_repeat_ngram_size=2
                )
                
            response = self.tokenizer.decode(outputs[0][inputs.shape[1]:], skip_special_tokens=True)
            
            # Пост-обработка ответа
            response = self._clean_response(response)
            
            if not response or len(response) < 15:
                response = self._get_smart_mock_response(message)
                
            self.add_message(chat_id, "assistant", response)
            return response
            
        except Exception as e:
            print(f"Error in get_response: {e}")
            return self._get_smart_mock_response(message)
    
    def _build_prompt(self, chat_id: int, message: str) -> str:
        messages = self.get_messages(chat_id)
        
        # Собираем историю
        history = ""
        for msg in messages[-10:]:
            if msg["role"] == "user":
                history += f"Человек: {msg['content']}\n"
            else:
                history += f"Консультант: {msg['content']}\n"
        
        prompt = f"""Ты CareerGuide - профессиональный карьерный консультант. Твоя задача - давать полезные советы по карьере, профессиональному развитию и выбору профессии.
Отвечай кратко, дружелюбно и по делу. Будь конкретным в своих рекомендациях.
{history}Человек: {message}
Консультант:"""
        
        return prompt
    
    def _get_smart_mock_response(self, message: str) -> str:
        """Умные заглушки для ответов"""
        message_lower = message.lower()
        
        # Приветствие
        if any(word in message_lower for word in ['привет', 'здравствуй', 'добрый', 'hello', 'hi']):
            return "Здравствуйте! Я CareerGuide, ваш карьерный консультант. Чем могу помочь в вопросах профессионального развития?"
        
        # Вопросы о карьере
        elif any(word in message_lower for word in ['карьер', 'професси', 'работ']):
            return "Для успешной карьеры важно постоянно обучаться и адаптироваться к изменениям на рынке труда."
        
        # Сетевые связи
        elif any(word in message_lower for word in ['сеть', 'контакт', 'знакомств']):
            return "Развитие сетевых связей и профессионального сообщества может открыть новые возможности для карьеры."
        
        # Навыки
        elif any(word in message_lower for word in ['навык', 'умение', 'компетенц']):
            return "Развитие soft skills (гибкие навыки) так же важно, как и технические знания. Уделяйте внимание коммуникации, лидерству и решению проблем."
        
        # Резюме
        elif any(word in message_lower for word in ['резюме', 'cv', 'анкет']):
            return "В резюме важно показать конкретные достижения и результаты. Используйте цифры и факты."
        
        # Собеседование
        elif any(word in message_lower for word in ['собеседован', 'интервью']):
            return "Подготовьтесь к собеседованию: изучите компанию, подготовьте вопросы и примеры своих достижений."
        
        # Обучение
        elif any(word in message_lower for word in ['обучен', 'курс', 'образован']):
            return "Непрерывное обучение - ключ к профессиональному росту. Рассмотрите онлайн-курсы, воркшопы и менторство."
        
        # Дела/состояние
        elif any(word in message_lower for word in ['дела', 'как ты', 'состояние']):
            return "Спасибо, что интересуетесь! Готова помочь с вашими карьерными вопросами."
        
        # По умолчанию
        else:
            return "Расскажите подробнее о вашей карьерной ситуации. Это поможет мне дать более точный совет."
    
    def _clean_response(self, response: str) -> str:
        # Убираем лишние части
        for stop_phrase in ["Человек:", "Пользователь:", "\n\n", "---"]:
            response = response.split(stop_phrase)[0]
        
        response = response.strip()
        
        # Убираем кавычки если они есть
        if response.startswith('"') and response.endswith('"'):
            response = response[1:-1]
            
        return response
chat_bot = CareerGuideBot()

# ниже два pydantic моделей

class QuizResults(BaseModel):
    A: int
    B: int
    C: int
    D: int


class UserSession(BaseModel):
    user_id: int
    ip_address: str

# Главные функции для реализации правильной логики логина, регистрации


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
        cursor.execute(
            'DELETE FROM quiz_progress WHERE user_id = ?', (user_id,))
        conn.commit()

# Роуты, некоторые используются, каак отдельные вычислительные функции


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

        print(
            f"Processing results: A={results.A}, B={results.B}, C={results.C}, D={results.D}")

        # Сохраняем ответы
        answers_string = f"A:{results.A},B:{results.B},C:{results.C},D:{results.D}"
        save_user_answers(user_id, answers_string, results.dict())

        # Очищаем прогресс теста
        clear_quiz_progress(user_id)

        return {"status": "success", "results": results.dict()}

    except Exception as e:
        print(f"Error processing results: {e}")
        return {"status": "error", "error": str(e)}

# Страницы профессий, пока не до конца реализовавшиеся


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

# функции для получения пользователей


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
            cursor.execute(
                "SELECT id, user_id, ip_address, created_at FROM user_sessions")
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

                bars = ax.bar(types, counts, color=colors,
                              edgecolor='black', linewidth=2, alpha=0.8)

                for bar, count in zip(bars, counts):
                    height = bar.get_height()
                    ax.text(bar.get_x() + bar.get_width()/2., height + 0.1,
                            f'{count}', ha='center', va='bottom', fontsize=14, fontweight='bold')

                ax.set_ylabel('Количество ответов',
                              fontsize=12, fontweight='bold')
                ax.set_xlabel('Типы личности', fontsize=12, fontweight='bold')
                ax.set_title('Результаты опросника', fontsize=16,
                             fontweight='bold', pad=20)
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


@app.get('/all', response_class=HTMLResponse)
def all_types_page(request: Request, user_id: int = Depends(get_current_user)):
    return templates.TemplateResponse("all.html", {
        "request": request,
        "user_id": user_id
    })

# Модели для чата, ненужно трогать, бесполезно


class ChatMessage(BaseModel):
    message: str


class CreateChatRequest(BaseModel):
    title: str = "Новый чат"

# Маршруты чат-бота, не нужно трогаь


@app.get('/chat_bot', response_class=HTMLResponse)
def chat_bot_page(request: Request, user_id: int = Depends(get_current_user)):
    return templates.TemplateResponse("chat_bot.html", {
        "request": request,
        "user_id": user_id
    })


@app.get('/chat/chats')
async def get_user_chats(
    request: Request,
    user_id: int = Depends(get_current_user)
):
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


@app.post('/chat/create')
async def create_chat(
    request: Request,
    create_request: CreateChatRequest,
    user_id: int = Depends(get_current_user)
):
    try:
        chat_id = chat_bot.create_chat(user_id, create_request.title)
        return {
            "status": "success",
            "chat_id": chat_id
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.post('/chat/{chat_id}/set_active')
async def set_active_chat(
    request: Request,
    chat_id: int,
    user_id: int = Depends(get_current_user)
):
    try:
        success = chat_bot.set_active_chat(user_id, chat_id)
        if success:
            return {"status": "success"}
        else:
            return {"status": "error", "error": "Chat not found"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.delete('/chat/{chat_id}')
async def delete_chat(
    request: Request,
    chat_id: int,
    user_id: int = Depends(get_current_user)
):
    try:
        success = chat_bot.delete_chat(user_id, chat_id)
        if success:
            return {"status": "success"}
        else:
            return {"status": "error", "error": "Chat not found"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


@app.get('/chat/messages')
async def get_chat_messages(
    request: Request,
    user_id: int = Depends(get_current_user)
):
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


@app.post('/chat/send')
async def send_message(
    request: Request,
    chat_message: ChatMessage,
    user_id: int = Depends(get_current_user)
):
    try:
        response = chat_bot.get_response(user_id, chat_message.message)
        return {
            "status": "success",
            "response": response
        }
    except Exception as e:
        return {"status": "error", "error": str(e)}
