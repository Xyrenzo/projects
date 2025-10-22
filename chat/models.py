from pydantic import BaseModel

class ChatMessage(BaseModel):
    message: str

class CreateChatRequest(BaseModel):
    title: str = "Новый чат"

class RenameChatRequest(BaseModel):
    title: str