from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from database.connection import init_db
from auth.router import router as auth_router
from quiz.router import router as quiz_router
from chat.router import router as chat_router
from results.router import router as results_router

app = FastAPI()

# иницииализация баз данныз
init_db()

# Serve static files
app.mount("/templates", StaticFiles(directory="templates"), name="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

# Подключение марщрутов
app.include_router(auth_router)
app.include_router(quiz_router)
app.include_router(chat_router)
app.include_router(results_router)