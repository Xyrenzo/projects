import google.generativeai as genai
from database.repositories import ChatRepository
from config import GEMINI_API_KEY

class CareerGuideBot:
    def __init__(self):
        try:
            genai.configure(api_key=GEMINI_API_KEY)
            self.model = genai.GenerativeModel('gemini-2.0-flash-exp')
            print("Гемини подключен успешно")
            
        except Exception as e:
            print(f"Ошибка при подключении: {e}")
            print("НАчнется использование заглушек")
            self.model = None

    def create_chat(self, user_id: int, title: str | None = None, first_message: str | None = None) -> int:
        """Создает чат с автоматическим названием на основе первого сообщения"""
        if title is None and first_message:
            title = self._generate_chat_title(first_message)
        elif title is None:
            title = "Новый чат"
        chat_id = ChatRepository.create_chat(user_id, title)
        ChatRepository.set_active_chat(user_id, chat_id)
        return chat_id
            
    
    def _generate_chat_title(self, first_message: str) -> str:
        """Генерирует название чата на основе первого сообщения"""
        if self.model is None:
            return self._generate_simple_title(first_message)
            
        try:
            prompt = f"""
            Придумай очень краткое и информативное название для чата карьерного консультанта.
            Основано на первом сообщении пользователя. Максимум 3-4 слова.
            Только название, без объяснений и кавычек.
            
            Сообщение: "{first_message[:200]}"
            
            Название:"""
            
            response = self.model.generate_content(
                prompt,
                generation_config=genai.types.GenerationConfig(
                    max_output_tokens=20,
                    temperature=0.3
                )
            )
            title = response.text.strip().replace('"', '').replace("'", "")
            
            # Валидация результата
            if not title or len(title) > 40:
                return self._generate_simple_title(first_message)
                
            return title
            
        except Exception as e:
            print(f"Ошибка генерации названия: {e}")
            return self._generate_simple_title(first_message)
    
    def _generate_simple_title(self, first_message: str) -> str:
        """Генерирует простое название для чата на основе первого сообщения"""
        if not first_message:
            return "Новый чат"
        
        # Берем первые 30 символов и добавляем многоточие если нужно
        title = first_message[:30]
        if len(first_message) > 30:
            title += "..."
        return title
    
    def get_chats(self, user_id: int):
        return ChatRepository.get_user_chats(user_id)
            
    def set_active_chat(self, user_id: int, chat_id: int) -> bool:
        return ChatRepository.set_active_chat(user_id, chat_id)
            
    def get_active_chat(self, user_id: int):
        return ChatRepository.get_active_chat(user_id)
            
    def delete_chat(self, user_id: int, chat_id: int) -> bool:
        return ChatRepository.delete_chat(user_id, chat_id)
        
    def rename_chat(self, user_id: int, chat_id: int, new_title: str) -> bool:
        return ChatRepository.rename_chat(user_id, chat_id, new_title)
            
    def add_message(self, chat_id: int, role: str, content: str):
        ChatRepository.add_message(chat_id, role, content)
        
    def get_messages(self, chat_id: int):
        return ChatRepository.get_messages(chat_id)
        
    def _get_user_test_results(self, user_id: int) -> dict:
        """Получает результаты теста пользователя из базы данных"""
        try:
            # Импортируем QuizRepository внутри метода чтобы избежать циклических импортов
            from database.repositories import QuizRepository
            
            # Получаем последние результаты теста пользователя
            results = QuizRepository.get_latest_results(user_id)
            if results:
                # results_json хранится как строка, конвертируем обратно в словарь
                import ast
                return ast.literal_eval(results[1]) if isinstance(results[1], str) else results[1]
            return {}
        except Exception as e:
            print(f"Ошибка при получении результатов теста: {e}")
            return {}
    
    def _get_user_profile(self, user_id: int) -> dict:
        """Получает профиль пользователя для глобальной памяти"""
        try:
            # Импортируем UserRepository внутри метода чтобы избежать циклических импортов
            from database.repositories import UserRepository
            
            # Получаем профиль пользователя
            profile = UserRepository.get_user_profile(user_id)
            return profile if profile else {}
        except Exception as e:
            print(f"Ошибка при получении профиля пользователя: {e}")
            return {}
        
    def get_response(self, user_id: int, message: str) -> str:
        if self.model is None:
            return self._get_smart_mock_response(message)
            
        try:
            active_chat = self.get_active_chat(user_id)
            if not active_chat:
                chat_id = self.create_chat(user_id, message[:30] + "..." if len(message) > 30 else message)
                active_chat = self.get_active_chat(user_id)
            else:
                chat_id = active_chat["id"]
                
            self.add_message(chat_id, "user", message)
            
            # Получаем историю сообщений (локальная память)
            messages = self.get_messages(chat_id)
            # Получаем результаты теста пользователя
            user_results = self._get_user_test_results(user_id)
            # Получаем профиль пользователя (глобальная память)
            user_profile = self._get_user_profile(user_id)
            prompt = self._build_prompt_with_history(messages, user_results, user_profile)
            response = self.model.generate_content(prompt)
            
            response_text = response.text.strip()
            
            # Если ответ пустой, используем ту заглушку, которая снизуу
            if not response_text:
                response_text = self._get_smart_mock_response(message)
                
            self.add_message(chat_id, "assistant", response_text)
            return response_text
            
        except Exception as e:
            print(f"Error in get_response: {e}")
            return self._get_smart_mock_response(message)
    
    def _build_prompt_with_history(self, messages: list, user_results: dict | None = None, user_profile: dict | None = None) -> str:
        """это промт"""
        # Начинаем с базового системного промпта
        system_prompt = """Ты — "Профорентолог" — умный ИИ-помощник, который помогает подросткам и студентам найти подходящую профессию, понять свои интересы и выбрать образовательный путь.

Твоя цель:
- Помогать пользователю определиться с будущей профессией.
- Давать советы по выбору направления обучения, вузов, программ и курсов.
- Использовать данные с интернета, чтобы находить актуальные сведения о профессиях, зарплатах, востребованности, и т.д.
- Давать вдохновляющие, но реалистичные советы.
- Поддерживать нейтральный и доброжелательный стиль общения, как у настоящего карьерного консультанта.

Тебе НЕЛЬЗЯ:
- Решать домашние задания, писать сочинения, рефераты и т.д.
- Отвечать на вопросы, не связанные с выбором профессии, образованием, карьерой или личным развитием.
- Давать личные данные, ссылки на сомнительные сайты, или что-то, что может быть небезопасно.

Если вопрос не по теме:
- Вежливо объясни, что ты предназначен только для помощи с профориентацией.
- Предложи задать вопрос, связанный с поиском профессии, направлением вуза или личными интересами.

Стиль общения:
- Пиши просто и коротко, понятно и дружелюбно.
- Используй примеры из реальной жизни.
- Можно чуть неформально, как будто ты современный наставник или ментор.

Примеры задач:
- "Помоги выбрать профессию по интересам."
- "Какие профессии подходят для человека, который любит анализировать и считать?"
- "Какие IT-направления сейчас перспективны?"
- "Как подготовиться к поступлению в NIS / Nazarbayev University / MIT?"
- "Как понять, подхожу ли я для медицины, инженерии, дизайна, бизнеса и т.д.?"

Отвечай чётко, структурированно, кратко, логично, используя абзацы, списки, подзаголовки.
Не используй лишние слова, избегай повторов.
Всегда сначала дай краткий ответ.
Пиши в нейтральном и уверенном тоне, будто объясняешь человеку, который хочет понять суть, а не просто услышать факт.
Если вопрос сложный — раздели ответ на пункты: основная идея, объяснение, пример, вывод.
Если можешь — добавь лёгкую визуальную структуру: списки, “—”, “:”, нумерацию.

"""
        
        # Добавляем глобальную память (профиль пользователя)
        if user_profile and isinstance(user_profile, dict):
            system_prompt += "\nГлобальная информация о пользователе:\n"
            for key, value in user_profile.items():
                if value:
                    field_names = {
                        "age": "Возраст",
                        "interests": "Интересы",
                        "strengths": "Сильные стороны",
                        "favorite_subjects": "Любимые предметы",
                        "goals": "Цели"
                    }
                    field_name = field_names.get(key, key)
                    system_prompt += f"- {field_name}: {value}\n"
        
        # Добавляем результаты теста пользователя
        if user_results and isinstance(user_results, dict):
            system_prompt += "\nРезультаты теста пользователя:\n"
            system_prompt += f"- Результаты теста: {user_results}\n"
            # Извлекаем основной тип, если он есть
            if 'A' in user_results and 'B' in user_results and 'C' in user_results and 'D' in user_results:
                # Определяем доминирующий тип
                max_type = max(user_results.items(), key=lambda x: x[1])
                system_prompt += f"- Основной тип личности: {self._get_type_name(max_type[0])} ({max_type[1]} баллов)\n"
        
        system_prompt += "\nИстория диалога:"
        
        # Добавляем последние 10 сообщений из истории (локальная память)
        conversation_history = ""
        for msg in messages[-10:]:
            if msg["role"] == "user":
                conversation_history += f"\nЧеловек: {msg['content']}"
            else:
                conversation_history += f"\nКонсультант: {msg['content']}"
        
        # Последнее сообщение пользователя
        last_user_message = messages[-1]["content"] if messages else ""
        
        full_prompt = f"{system_prompt}{conversation_history}\n\nТекущий вопрос: {last_user_message}\n\nТвой ответ:"
        
        return full_prompt
    
    def _get_type_name(self, type_letter: str) -> str:
        """Возвращает название типа по букве"""
        type_names = {
            "A": "Практик-деятель",
            "B": "Коммуникатор-организатор",
            "C": "Творец-иноватор",
            "D": "Аналитик-стратег"
        }
        return type_names.get(type_letter, "Неизвестный тип")
    
    def _get_smart_mock_response(self, message: str) -> str:
        """ЗАглушки, которые обязательны"""
        message_lower = message.lower()
        
        # Приветствие
        if any(word in message_lower for word in ['привет', 'здравствуй', 'добрый', 'hello', 'hi']):
            return "Здравствуйте! Я Профорентолог - ваш ИИ-помощник по выбору профессии. Чем могу помочь в вопросах профессионального развития?"
        
        # Вопросы о профессиях
        elif any(word in message_lower for word in ['професси', 'работ', 'карьер']):
            return "Для выбора подходящей профессии важно понимать свои интересы и способности. Расскажите подробнее о том, что вам нравится делать, и я помогу подобрать подходящие направления."
        
        # Вопросы об образовании
        elif any(word in message_lower for word in ['образован', 'вуз', 'университет', 'поступл', 'курс']):
            return "Выбор образовательного направления зависит от ваших интересов и целей. Рекомендую изучить профильные предметы, поговорить с действующими специалистами и пройти практику в интересующей сфере."
        
        # Вопросы о навыках
        elif any(word in message_lower for word in ['навык', 'умение', 'компетенц']):
            return "Развитие профессиональных навыков - ключ к успеху. Сосредоточьтесь на тех областях, которые соответствуют выбранной профессии, и не забывайте о soft skills - коммуникации, критическом мышлении и творчестве."
        
        # Вопросы о рынке труда
        elif any(word in message_lower for word in ['зарплат', 'востребован', 'рынок', 'перспектив']):
            return "Актуальную информацию о рынке труда можно найти на профильных сайтах по трудоустройству. Важно учитывать не только текущую востребованность, но и перспективы развития направления."
        
        # Вопросы о личных качествах
        elif any(word in message_lower for word in ['интерес', 'качеств', 'способност', 'люблю']):
            return "Понимание своих интересов и качеств - первый шаг к правильному выбору профессии. Подумайте, что вам действительно нравится делать, и в каких ситуациях вы чувствуетесь наиболее уверенно."
        
        # Вне темы
        elif any(word in message_lower for word in ['домашк', 'сочинен', 'реферат', 'математик', 'физик']):
            return "Извините, но я специализируюсь только на вопросах профориентации и выбора профессии. Пожалуйста, задайте вопрос, связанный с профессиональным развитием или выбором образовательного направления."
        else:
            return "Расскажите подробнее о ваших интересах и целях в профессиональной сфере. Это поможет мне дать более точный и полезный совет по выбору профессии."