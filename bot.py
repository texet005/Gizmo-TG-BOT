# -----------------------------------
# ИМПОРТЫ
# -----------------------------------
import asyncio
import os
import httpx
import jwt
from aiogram import Bot, Dispatcher, F
from aiogram.client.default import DefaultBotProperties
from aiogram.types import (
    Message, KeyboardButton, ReplyKeyboardMarkup,
    InlineKeyboardButton, InlineKeyboardMarkup, CallbackQuery
)
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage
from dotenv import load_dotenv

# --- новые импорты для сохранения сессий ---
import json
from pathlib import Path
import stat

# -----------------------------------
# ЗАГРУЗКА КОНФИГА
# -----------------------------------
env_path = os.path.join(os.path.dirname(__file__), "config.env")
print(f"DEBUG: config.env path = {env_path}")
load_dotenv(env_path)

BOT_TOKEN = os.getenv("BOT_TOKEN")

# -----------------------------------
# Измените только IP!!! /api не изменяйте
# -----------------------------------
API_BASE = "https://0.0.0.0/api"

# -----------------------------------
# ЗАГРУЗКА ДАННЫХ АДМИНОВ
# -----------------------------------
ADMIN_TELEGRAM_ID = int(os.getenv("ADMIN_TELEGRAM_ID", "сюда вставьте данные с config.env"))
ADMINS_CHAT_ID = int(os.getenv("ADMINS_CHAT_ID", "сюда вставьте данные с config.env"))
ADMIN_NICKS = json.loads(os.getenv("ADMIN_NICKS", 'сюда вставьте данные с config.env'))

sessions = {}
admin_token = None

# -----------------------------------
# ФАЙЛ СЕССИЙ И АКТИВНЫХ ЧАТОВ
# -----------------------------------
SESSIONS_FILE = Path(__file__).with_name("sessions.json")
ACTIVE_CHATS_FILE = Path(__file__).with_name("active_chats.json")
ADMINS_FILE = Path(__file__).with_name("admins.json")

def load_sessions():
    global sessions
    try:
        if SESSIONS_FILE.exists():
            with SESSIONS_FILE.open("r", encoding="utf-8") as f:
                raw = json.load(f)
            sessions = {int(k): v for k, v in raw.items()}
            print(f"✅ Загружено {len(sessions)} сессий из {SESSIONS_FILE}")
        else:
            sessions = {}
    except Exception as e:
        print(f"⚠️ Не удалось загрузить {SESSIONS_FILE}: {e}")
        sessions = {}

def save_sessions():
    try:
        tmp = SESSIONS_FILE.with_suffix(".tmp")
        data_to_write = {str(k): v for k, v in sessions.items()}
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(data_to_write, f, ensure_ascii=False, indent=2)
        tmp.replace(SESSIONS_FILE)
        try:
            SESSIONS_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
        print(f"✅ Сессии сохранены в {SESSIONS_FILE}")
    except Exception as e:
        print(f"❌ Не удалось сохранить сессии: {e}")

def load_active_chats():
    try:
        if ACTIVE_CHATS_FILE.exists():
            with ACTIVE_CHATS_FILE.open("r", encoding="utf-8") as f:
                return json.load(f)
        return {}
    except Exception as e:
        print(f"⚠️ Не удалось загрузить активные чаты: {e}")
        return {}

def save_active_chats(active_chats):
    try:
        tmp = ACTIVE_CHATS_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(active_chats, f, ensure_ascii=False, indent=2)
        tmp.replace(ACTIVE_CHATS_FILE)
        try:
            ACTIVE_CHATS_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
    except Exception as e:
        print(f"❌ Не удалось сохранить активные чаты: {e}")

def load_admins():
    try:
        if ADMINS_FILE.exists():
            with ADMINS_FILE.open("r", encoding="utf-8") as f:
                admins_data = json.load(f)
            # Объединяем с админами из config.env (приоритет у файла admins.json)
            merged_admins = {**ADMIN_NICKS, **admins_data}
            return merged_admins
        return ADMIN_NICKS
    except Exception as e:
        print(f"⚠️ Не удалось загрузить список администраторов: {e}")
        return ADMIN_NICKS

def save_admins(admins_dict):
    try:
        tmp = ADMINS_FILE.with_suffix(".tmp")
        with tmp.open("w", encoding="utf-8") as f:
            json.dump(admins_dict, f, ensure_ascii=False, indent=2)
        tmp.replace(ADMINS_FILE)
        try:
            ADMINS_FILE.chmod(stat.S_IRUSR | stat.S_IWUSR)
        except Exception:
            pass
        print(f"✅ Список администраторов сохранен")
    except Exception as e:
        print(f"❌ Не удалось сохранить список администраторов: {e}")

# -----------------------------------
# Координаты и ссылки из config.env
# -----------------------------------
CLUB_LAT = os.getenv("CLUB_LAT")
CLUB_LON = os.getenv("CLUB_LON")
VK_GROUP_URL = os.getenv("VK_GROUP_URL")

user_messages = {}
active_chats = load_active_chats()
ADMIN_NICKS = load_admins()

# -----------------------------------
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ДЛЯ АДМИНОВ
# -----------------------------------
def is_admin(user_id: int) -> bool:
    return str(user_id) in ADMIN_NICKS

def get_admin_menu():
    kb = [
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="💰 Баланс")],
        [KeyboardButton(text="📍 Где находимся?")],
        [KeyboardButton(text="🖥 Доступные ПК")],
        [KeyboardButton(text="💬 Чат с администратором")],
        [KeyboardButton(text="⚙️ Управление администраторами")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

# -----------------------------------
# КНОПКИ ГЛАВНОГО МЕНЮ + УПРАВЛЕНИЕ АДМИНИСТРАТОРА С admins
# -----------------------------------
def menu():
    kb = [
        [KeyboardButton(text="👤 Профиль"), KeyboardButton(text="💰 Баланс")],
        [KeyboardButton(text="📍 Где находимся?")],
        [KeyboardButton(text="🖥 Доступные ПК")],
        [KeyboardButton(text="💬 Чат с администратором")],
    ]
    return ReplyKeyboardMarkup(keyboard=kb, resize_keyboard=True)

def admin_chat_menu(user_id):
    kb = [
        [InlineKeyboardButton(text="📨 Ответить", callback_data=f"reply_to:{user_id}")],
        [InlineKeyboardButton(text="🔒 Закрыть чат", callback_data=f"close_chat:{user_id}")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def user_chat_menu():
    kb = [
        [InlineKeyboardButton(text="🔒 Закрыть чат", callback_data="close_chat_user")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

def admin_management_menu():
    kb = [
        [InlineKeyboardButton(text="➕ Добавить администратора", callback_data="add_admin")],
        [InlineKeyboardButton(text="🗑 Удалить администратора", callback_data="remove_admin")],
        [InlineKeyboardButton(text="📋 Список администраторов", callback_data="list_admins")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]
    ]
    return InlineKeyboardMarkup(inline_keyboard=kb)

# -----------------------------------
# УДАЛЕНИЕ СООБЩЕНИЙ
# -----------------------------------
async def cleanup_messages(m: Message):
    uid = m.from_user.id
    try:
        await m.delete()
    except Exception:
        pass
    if uid in user_messages:
        for msg_id in user_messages[uid]:
            try:
                await m.bot.delete_message(chat_id=uid, message_id=msg_id)
            except Exception:
                pass
        user_messages[uid] = []

# -----------------------------------
# ЛОГИН АДМИНА
# -----------------------------------
async def login_admin():
    global admin_token
    url = f"{API_BASE}/v2.0/auth/accesstoken?Username=admin&Password=admin"
    async with httpx.AsyncClient(verify=False) as client:
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            admin_token = data["result"]["token"]
            print("✅ Админ авторизован")
            return True
        print("❌ Не удалось авторизовать админа")
        return False

# -----------------------------------
# ЛОГИН ПОЛЬЗОВАТЕЛЯ
# -----------------------------------
async def login_client(tg_id: int, username: str, password: str):
    url = f"{API_BASE}/user/v2.0/auth/accesstoken?Username={username}&Password={password}"
    async with httpx.AsyncClient(verify=False) as client:
        r = await client.get(url)
        if r.status_code == 200:
            data = r.json()
            token = data["result"]["token"]
            payload = jwt.decode(token, options={"verify_signature": False})
            user_id = payload.get("nameid")
            sessions[tg_id] = {
                "token": token,
                "user_id": user_id,
                "login": username,
                "password": password
            }
            save_sessions()
            return True
        return False

# -----------------------------------
# ПРОФИЛЬ
# -----------------------------------
async def get_profile(tg_id: int):
    user_data = sessions.get(tg_id)
    if not user_data:
        return None
    url = f"{API_BASE}/v2.0/users/{user_data['user_id']}"
    headers = {"Authorization": f"Bearer {admin_token}"}
    async with httpx.AsyncClient(verify=False) as client:
        r = await client.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()["result"]
    return None

# -----------------------------------
# БАЛАНС
# -----------------------------------
async def get_balance(tg_id: int):
    user_data = sessions.get(tg_id)
    if not user_data:
        return None
    url = f"{API_BASE}/users/{user_data['user_id']}/balance"
    headers = {"Authorization": f"Bearer {admin_token}"}
    async with httpx.AsyncClient(verify=False) as client:
        r = await client.get(url, headers=headers)
        if r.status_code == 200:
            return r.json()["result"]
    return None

# -----------------------------------
# ДОСТУПНЫЕ ПК (НОВАЯ ЛОГИКА)
# -----------------------------------
async def get_available_hosts():
    headers = {"Authorization": f"Bearer {admin_token}"}
    async with httpx.AsyncClient(verify=False) as client:
        # Получаем активные сессии
        active_resp = await client.get(f"{API_BASE}/usersessions/activeinfo", headers=headers)
        active_hosts = set()
        if active_resp.status_code == 200:
            active_data = active_resp.json().get("result", [])
            active_hosts = {s["hostId"] for s in active_data if s.get("hostId")}

        # Получаем список всех ПК
        hosts_resp = await client.get(f"{API_BASE}/hosts", headers=headers)
        if hosts_resp.status_code != 200:
            return []

        hosts = hosts_resp.json().get("result", [])
        available = []

        for h in hosts:
            if not h.get("isDeleted") and h.get("id") not in active_hosts:
                available.append(h)

        return available

# -----------------------------------
# ЛОГИН НА ПК
# -----------------------------------
async def login_to_host(tg_id: int, host_id: int):
    user_data = sessions.get(tg_id)
    if not user_data:
        return False, "❌ Сначала войдите в систему"
    user_id = user_data["user_id"]
    headers = {"Authorization": f"Bearer {admin_token}"}
    async with httpx.AsyncClient(verify=False) as client:
        # логин
        url_login = f"{API_BASE}/users/{user_id}/login/{host_id}"
        r1 = await client.post(url_login, headers=headers)
        if r1.status_code != 200:
            return False, "❌ Ошибка при входе на ПК"
        # unlock
        url_unlock = f"{API_BASE}/hosts/{host_id}/lock/false"
        r2 = await client.post(url_unlock, headers=headers)
        if r2.status_code != 200:
            return False, "⚠️ Вход выполнен, но не удалось снять блокировку"
    return True, "✅ Успешный вход"

# -----------------------------------
# FSM
# -----------------------------------
class AuthState(StatesGroup):
    waiting_for_login = State()
    waiting_for_password = State()

class ChatState(StatesGroup):
    waiting_for_user_message = State()
    waiting_for_admin_reply = State()

class AdminManagementState(StatesGroup):
    waiting_for_admin_id = State()
    waiting_for_admin_name = State()
    waiting_for_admin_remove = State()

dp = Dispatcher(storage=MemoryStorage())

# -----------------------------------
# START И ФУНКЦИЯ ЛОГИНА ПОЛЬЗОВАТЕЛЯ ПО ДАННЫМ GIZMO
# -----------------------------------
@dp.message(F.text == "/start")
async def start_cmd(m: Message, state: FSMContext):
    await cleanup_messages(m)
    await state.set_state(AuthState.waiting_for_login)
    
    # Показываем разное меню для админов и обычных пользователей
    if is_admin(m.from_user.id):
        menu_markup = get_admin_menu()
    else:
        menu_markup = menu()
    
    msg = await m.answer("👋 Добро пожаловать в клуб!\nДанный бот нужен для просмотра баланса, профиля в клубе, а так-же автоматического входа в ПК.\nДля продолжения введите ваш логин:", reply_markup=menu_markup)
    user_messages[m.from_user.id] = [msg.message_id]

@dp.message(AuthState.waiting_for_login)
async def process_login(m: Message, state: FSMContext):
    await cleanup_messages(m)
    await state.update_data(login=m.text)
    await state.set_state(AuthState.waiting_for_password)
    msg = await m.answer("🔑 Теперь введите пароль:")
    user_messages[m.from_user.id] = [msg.message_id]

@dp.message(AuthState.waiting_for_password)
async def process_password(m: Message, state: FSMContext):
    await cleanup_messages(m)
    data = await state.get_data()
    login = data["login"]
    password = m.text
    if await login_client(m.from_user.id, login, password):
        # Показываем разное меню для админов и обычных пользователей
        if is_admin(m.from_user.id):
            menu_markup = get_admin_menu()
        else:
            menu_markup = menu()
            
        msg = await m.answer("✅ Успешный вход!", reply_markup=menu_markup)
        user_messages[m.from_user.id] = [msg.message_id]
        await state.clear()
    else:
        msg = await m.answer("❌ Ошибка авторизации, проверьте логин и пароль, а потом попробуйте снова с /start")
        user_messages[m.from_user.id] = [msg.message_id]
        await state.clear()

# -----------------------------------
# УПРАВЛЕНИЕ АДМИНИСТРАТОРАМИ
# -----------------------------------
@dp.message(F.text == "⚙️ Управление администраторами")
async def admin_management(m: Message):
    if not is_admin(m.from_user.id):
        await m.answer("❌ У вас нет прав для доступа к этому разделу")
        return
    
    await cleanup_messages(m)
    msg = await m.answer("⚙️ Управление администраторами:", reply_markup=admin_management_menu())
    user_messages[m.from_user.id] = [msg.message_id]

@dp.callback_query(F.data == "add_admin")
async def add_admin_start(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        await c.answer("❌ У вас нет прав для этой операции", show_alert=True)
        return
    
    await state.set_state(AdminManagementState.waiting_for_admin_id)
    await c.message.answer("👤 Введите Telegram ID нового администратора:")
    await c.answer()

@dp.message(AdminManagementState.waiting_for_admin_id)
async def process_admin_id(m: Message, state: FSMContext):
    try:
        admin_id = int(m.text.strip())
        await state.update_data(admin_id=admin_id)
        await state.set_state(AdminManagementState.waiting_for_admin_name)
        await m.answer("📝 Теперь введите имя для нового администратора:")
    except ValueError:
        await m.answer("❌ Неверный формат ID. Введите числовой Telegram ID:")

@dp.message(AdminManagementState.waiting_for_admin_name)
async def process_admin_name(m: Message, state: FSMContext):
    data = await state.get_data()
    admin_id = data['admin_id']
    admin_name = m.text.strip()
    
    # Добавляем администратора
    ADMIN_NICKS[str(admin_id)] = admin_name
    save_admins(ADMIN_NICKS)
    
    await m.answer(f"✅ Администратор добавлен!\nID: {admin_id}\nИмя: {admin_name}")
    await state.clear()

@dp.callback_query(F.data == "remove_admin")
async def remove_admin_start(c: CallbackQuery, state: FSMContext):
    if not is_admin(c.from_user.id):
        await c.answer("❌ У вас нет прав для этой операции", show_alert=True)
        return
    
    # Создаем клавиатуру с администраторами для удаления
    if len(ADMIN_NICKS) <= 1:
        await c.answer("❌ Нельзя удалить последнего администратора", show_alert=True)
        return
    
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=f"{name} (ID: {id})", callback_data=f"remove_admin_confirm:{id}")] 
        for id, name in ADMIN_NICKS.items() if int(id) != c.from_user.id
    ] + [[InlineKeyboardButton(text="⬅️ Отмена", callback_data="cancel_remove")]])
    
    await c.message.answer("🗑 Выберите администратора для удаления:", reply_markup=kb)
    await c.answer()

@dp.callback_query(F.data.startswith("remove_admin_confirm:"))
async def remove_admin_confirm(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("❌ У вас нет прав для этой операции", show_alert=True)
        return
    
    admin_id = c.data.split(":")[1]
    admin_name = ADMIN_NICKS.get(admin_id, "Неизвестно")
    
    # Не позволяем удалить себя
    if int(admin_id) == c.from_user.id:
        await c.answer("❌ Нельзя удалить самого себя", show_alert=True)
        return
    
    # Удаляем администратора
    del ADMIN_NICKS[admin_id]
    save_admins(ADMIN_NICKS)
    
    await c.message.edit_text(f"✅ Администратор удален:\nID: {admin_id}\nИмя: {admin_name}")
    await c.answer()

@dp.callback_query(F.data == "cancel_remove")
async def cancel_remove(c: CallbackQuery):
    await c.message.edit_text("❌ Удаление отменено")
    await c.answer()

@dp.callback_query(F.data == "list_admins")
async def list_admins(c: CallbackQuery):
    if not is_admin(c.from_user.id):
        await c.answer("❌ У вас нет прав для этой операции", show_alert=True)
        return
    
    admins_list = "📋 Список администраторов:\n\n"
    for admin_id, admin_name in ADMIN_NICKS.items():
        admins_list += f"👤 {admin_name} (ID: {admin_id})\n"
    
    await c.message.answer(admins_list)
    await c.answer()

@dp.callback_query(F.data == "back_to_menu")
async def cb_back_to_menu(c: CallbackQuery):
    try:
        await c.message.delete()
    except Exception:
        pass
    # Показываем разное меню для админов и обычных пользователей
    if is_admin(c.from_user.id):
        menu_markup = get_admin_menu()
    else:
        menu_markup = menu()
    await c.message.answer("🔙 Возврат в меню", reply_markup=menu_markup)
    await c.answer()

# -----------------------------------
# ЧАТ С АДМИНИСТРАТОРОМ \ ФУНКЦИИ ЧАТОВ \ ПРИВЯЗКА СЕТКИ
# -----------------------------------
@dp.message(F.text == "💬 Чат с администратором")
async def start_admin_chat(m: Message, state: FSMContext):
    await cleanup_messages(m)
    user_id = m.from_user.id
    
    # Получаем информацию о пользователе
    profile_data = await get_profile(user_id)
    username = profile_data.get('username', 'Неизвестно') if profile_data else 'Неизвестно'
    first_name = profile_data.get('firstName', 'Неизвестно') if profile_data else 'Неизвестно'
    
    # Создаем активный чат
    active_chats[str(user_id)] = {
        "username": username,
        "first_name": first_name,
        "active": True
    }
    save_active_chats(active_chats)
    
    # Отправляем уведомление в чат администраторов
    admin_message = f"👤 Новое сообщение от пользователя:\n\nID: {user_id}\nИмя: {first_name}\nНик: {username}\n\nСообщение:"
    await m.bot.send_message(
        ADMINS_CHAT_ID, 
        admin_message,
        reply_markup=admin_chat_menu(user_id)
    )
    
    msg = await m.answer(
        "💬 Чат с администратором открыт. Напишите ваше сообщение:\n\n"
        "Вы можете отправлять текст или фото.",
        reply_markup=user_chat_menu()
    )
    user_messages[user_id] = [msg.message_id]
    await state.set_state(ChatState.waiting_for_user_message)

@dp.message(ChatState.waiting_for_user_message)
async def process_user_message(m: Message, state: FSMContext):
    user_id = m.from_user.id
    
    if not active_chats.get(str(user_id), {}).get("active", False):
        # Показываем разное меню для админов и обычных пользователей
        if is_admin(m.from_user.id):
            menu_markup = get_admin_menu()
        else:
            menu_markup = menu()
        await m.answer("❌ Чат закрыт. Нажмите '💬 Чат с администратором' чтобы открыть заново.", reply_markup=menu_markup)
        await state.clear()
        return
    
    # Отправляем сообщение в чат администраторов
    if m.text:
        admin_message = f"👤 Сообщение от {m.from_user.first_name} (ID: {user_id}):\n\n{m.text}"
        await m.bot.send_message(
            ADMINS_CHAT_ID, 
            admin_message,
            reply_markup=admin_chat_menu(user_id)
        )
        await m.answer("✅ Сообщение отправлено администратору", reply_markup=user_chat_menu())
    
    elif m.photo:
        # Отправляем фото в чат администраторов
        caption = f"👤 Фото от {m.from_user.first_name} (ID: {user_id})"
        if m.caption:
            caption += f"\n\nПодпись: {m.caption}"
            
        await m.bot.send_photo(
            ADMINS_CHAT_ID,
            m.photo[-1].file_id,
            caption=caption,
            reply_markup=admin_chat_menu(user_id)
        )
        await m.answer("✅ Фото отправлено администратору", reply_markup=user_chat_menu())

@dp.callback_query(F.data.startswith("reply_to:"))
async def start_admin_reply(c: CallbackQuery, state: FSMContext):
    user_id = int(c.data.split(":")[1])
    
    # Проверяем права администратора
    if not is_admin(c.from_user.id):
        await c.answer("❌ У вас нет прав для ответа", show_alert=True)
        return
    
    await state.update_data(reply_to_user=user_id)
    await state.set_state(ChatState.waiting_for_admin_reply)
    
    await c.message.answer(f"💬 Введите ответ для пользователя (ID: {user_id}):")
    await c.answer()

@dp.message(ChatState.waiting_for_admin_reply)
async def process_admin_reply(m: Message, state: FSMContext):
    data = await state.get_data()
    user_id = data.get('reply_to_user')
    
    if not user_id:
        await m.answer("❌ Ошибка: пользователь не найден")
        await state.clear()
        return
    
    # Получаем имя администратора
    admin_name = ADMIN_NICKS.get(str(m.from_user.id), "Администратор")
    
    try:
        # Отправляем ответ пользователю
        await m.bot.send_message(
            user_id,
            f"💌 Ответ от {admin_name}:\n\n{m.text}\n\n"
            f"Для продолжения общения отправьте новое сообщение.",
            reply_markup=user_chat_menu()
        )
        
        # Уведомляем администратора
        await m.answer("✅ Ответ отправлен пользователю")
        
        # Обновляем состояние чата
        active_chats[str(user_id)] = {
            **active_chats.get(str(user_id), {}),
            "active": True
        }
        save_active_chats(active_chats)
        
    except Exception as e:
        await m.answer(f"❌ Не удалось отправить сообщение пользователю: {e}")
    
    await state.clear()

# -----------------------------------
# ФУНКЦИЯ ЗАКРЫТИЯ ЧАТА АДМИНОМ
# -----------------------------------

@dp.callback_query(F.data.startswith("close_chat:"))
async def close_chat_by_admin(c: CallbackQuery):
    user_id = int(c.data.split(":")[1])
    
    # Проверяем права администратора
    if not is_admin(c.from_user.id):
        await c.answer("❌ У вас нет прав для закрытия чата", show_alert=True)
        return
    
    # Закрываем чат
    if str(user_id) in active_chats:
        active_chats[str(user_id)]["active"] = False
        save_active_chats(active_chats)
    
    try:
        # Уведомляем пользователя
        await c.bot.send_message(
            user_id,
            "🔒 Администратор закрыл чат. Если у вас остались вопросы, "
            "нажмите '💬 Чат с администратором' чтобы открыть новый чат.",
            reply_markup=menu()
        )
    except Exception:
        pass
    
    await c.message.edit_text(f"✅ Чат с пользователем {user_id} закрыт")
    await c.answer()

# -----------------------------------
# ФУНКЦИЯ ЗАКРЫТИЯ ЧАТА ПОЛЬЗОВАТЕЛЕМ
# -----------------------------------
@dp.callback_query(F.data == "close_chat_user")
async def close_chat_by_user(c: CallbackQuery, state: FSMContext):
    user_id = c.from_user.id
    
    # Закрываем чат
    if str(user_id) in active_chats:
        active_chats[str(user_id)]["active"] = False
        save_active_chats(active_chats)
    
    await c.message.edit_text(
        "🔒 Вы закрыли чат. Если у вас остались вопросы, "
        "нажмите '💬 Чат с администратором' чтобы открыть новый чат."
    )
    await c.answer()
    await state.clear()

# -----------------------------------
# КНОПКИ
# -----------------------------------
@dp.message(F.text == "👤 Профиль")
async def profile(m: Message):
    await cleanup_messages(m)
    data = await get_profile(m.from_user.id)
    if data:
        # Показываем разное меню для админов и обычных пользователей
        if is_admin(m.from_user.id):
            menu_markup = get_admin_menu()
        else:
            menu_markup = menu()
            
        msg = await m.answer(
            f"👤 Профиль\nТелефон: {data['mobilePhone']}\n"
            f"Ник: {data['username']}\nИмя: {data.get('firstName')}",
            reply_markup=menu_markup
        )
    else:
        msg = await m.answer("❌ Ошибка при получении профиля", reply_markup=menu())
    user_messages[m.from_user.id] = [msg.message_id]

@dp.message(F.text == "💰 Баланс")
async def balance(m: Message):
    await cleanup_messages(m)
    data = await get_balance(m.from_user.id)
    if data:
        # Показываем разное меню для админов и обычных пользователей
        if is_admin(m.from_user.id):
            menu_markup = get_admin_menu()
        else:
            menu_markup = menu()
            
        deposits = data.get("deposits", 0)
        points = data.get("points", 0)
        msg = await m.answer(
            f"💰 Баланс\nДепозит: {deposits} ₽\nБаллы: {points}",
            reply_markup=menu_markup
        )
    else:
        msg = await m.answer("❌ Баланс не найден", reply_markup=menu())
    user_messages[m.from_user.id] = [msg.message_id]

@dp.message(F.text == "📍 Где находимся?")
async def club_location(m: Message):
    await cleanup_messages(m)
    uid = m.from_user.id
    user_messages[uid] = []
    loc_msg = await m.answer_location(latitude=float(CLUB_LAT), longitude=float(CLUB_LON))
    user_messages[uid].append(loc_msg.message_id)
    
    # Показываем разное меню для админов и обычных пользователей
    if is_admin(m.from_user.id):
        menu_markup = get_admin_menu()
    else:
        menu_markup = menu()
        
    txt_msg = await m.answer("Мы находимся здесь 👇", reply_markup=menu_markup)
    user_messages[uid].append(txt_msg.message_id)
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(
            text="🗺 Яндекс.Карты",
            url=f"https://yandex.ru/maps/?pt={CLUB_LON},{CLUB_LAT}&z=17&l=map"
        )],
        [InlineKeyboardButton(
            text="📍 2ГИС",
            url=f"https://2gis.ru/search/{CLUB_LAT}%2C{CLUB_LON}/zoom/17"
        )],
        [InlineKeyboardButton(
            text="🔗 Группа ВК",
            url=VK_GROUP_URL
        )]
    ])
    kb_msg = await m.answer("Выберите действие:", reply_markup=kb)
    user_messages[uid].append(kb_msg.message_id)

@dp.message(F.text == "🖥 Доступные ПК")
async def available_pcs(m: Message):
    await cleanup_messages(m)
    hosts = await get_available_hosts()
    if hosts:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=h["name"], callback_data=f"login_host:{h['id']}")] for h in hosts
        ] + [[InlineKeyboardButton(text="⬅️ Назад", callback_data="back_to_menu")]])
        msg = await m.answer("🖥 Выберите ПК для входа:", reply_markup=kb)
    else:
        msg = await m.answer("❌ Свободных ПК нет", reply_markup=menu())
    user_messages[m.from_user.id] = [msg.message_id]

@dp.callback_query(F.data.startswith("login_host:"))
async def cb_login_host(c: CallbackQuery):
    host_id = int(c.data.split(":")[1])
    ok, text = await login_to_host(c.from_user.id, host_id)
    
    # Показываем разное меню для админов и обычных пользователей
    if is_admin(c.from_user.id):
        menu_markup = get_admin_menu()
    else:
        menu_markup = menu()
        
    await c.message.answer(text, reply_markup=menu_markup)
    await c.answer()

# -----------------------------------
# MAIN
# -----------------------------------
async def main():
    load_sessions()
    await login_admin()
    bot = Bot(token=BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())