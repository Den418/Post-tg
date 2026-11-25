"""Telegram post formatter bot built with aiogram 3."""

from __future__ import annotations

import html
import os
import secrets
from typing import Any

from aiogram import Bot, Dispatcher, F, Router
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    InlineQuery,
    InlineQueryResultCachedPhoto,
    KeyboardButton,
    Message,
    ReplyKeyboardMarkup,
    SwitchInlineQueryChosenChat,
)
from aiogram.client.default import DefaultBotProperties


def load_dotenv() -> None:
    """Load .env values without overriding variables already in the environment."""
    try:
        with open(os.path.join(os.path.dirname(__file__), ".env"), encoding="utf-8") as env_file:
            for raw_line in env_file:
                line = raw_line.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                name, value = line.split("=", 1)
                os.environ.setdefault(name.strip(), value.strip().strip('"').strip("'"))
    except FileNotFoundError:
        pass


load_dotenv()
TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
ALLOWED_USER_IDS = {
    int(part.strip())
    for part in os.environ.get("ALLOWED_USER_IDS", "").split(",")
    if part.strip().isdigit()
}

BTN_CREATE = "➕ Создать пост"
BTN_BACK = "⬅️ Назад"
BTN_CANCEL = "❌ Отмена"
BTN_RESTART = "🔄 Начать заново"

EMOJI = {
    "fire": '<tg-emoji emoji-id="5312241539987020022">🔥</tg-emoji>',
    "alien": '<tg-emoji emoji-id="5370869711888194012">👾</tg-emoji>',
    "chat": '<tg-emoji emoji-id="5138673149822370362">💬</tg-emoji>',
    "pin": '<tg-emoji emoji-id="4929530413128352588">📌</tg-emoji>',
    "check": '<tg-emoji emoji-id="5206607081334906820">✔️</tg-emoji>',
}

router = Router()
dispatcher = Dispatcher(storage=MemoryStorage())
dispatcher.include_router(router)
ready_posts: dict[str, dict[str, str]] = {}


class PostForm(StatesGroup):
    title = State()
    description = State()
    tags = State()
    version = State()
    mod = State()
    photo = State()


FORM_STATES = [PostForm.title, PostForm.description, PostForm.tags, PostForm.version, PostForm.mod, PostForm.photo]
PROMPTS = {
    PostForm.title.state: "Пришлите название поста.",
    PostForm.description.state: "Теперь пришлите небольшое описание.",
    PostForm.tags.state: "Пришлите тег или несколько тегов (например: #игра #читы).",
    PostForm.version.state: "Укажите версию.",
    PostForm.mod.state: "Опишите мод и его возможности.",
    PostForm.photo.state: "Теперь пришлите картинку для поста.",
}


def allowed(user_id: int | None) -> bool:
    return user_id is not None and user_id in ALLOWED_USER_IDS


def main_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text=BTN_CREATE)]],
        resize_keyboard=True,
        is_persistent=True,
    )


def stage_keyboard(step_index: int) -> ReplyKeyboardMarkup:
    rows: list[list[KeyboardButton]] = []
    if step_index > 0:
        rows.append([KeyboardButton(text=BTN_BACK)])
    rows.append([KeyboardButton(text=BTN_CANCEL), KeyboardButton(text=BTN_RESTART)])
    return ReplyKeyboardMarkup(keyboard=rows, resize_keyboard=True, is_persistent=True)


def escape(value: str) -> str:
    return html.escape(value, quote=False)


def format_post(post: dict[str, str]) -> str:
    return (
        f"{EMOJI['alien']} <b>{escape(post['title'])}</b> {EMOJI['alien']}\n\n"
        f"{EMOJI['fire']} <i>{escape(post['description'])}</i> {EMOJI['fire']}\n\n"
        f"<blockquote>{EMOJI['pin']} Теги: {escape(post['tags'])}\n"
        f"{EMOJI['chat']} Версия: {escape(post['version'])}</blockquote>\n\n"
        f"{EMOJI['check']} <b>Мод: {escape(post['mod'])}</b>"
    )


def share_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(
            text="↗ Переслать в чат",
            switch_inline_query_chosen_chat=SwitchInlineQueryChosenChat(
                query=token,
                allow_user_chats=True,
                allow_group_chats=True,
                allow_channel_chats=True,
            ),
        )
    ]])


async def begin(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(PostForm.title)
    await message.answer("Создаём новый пост.\nШаг 1 из 6. " + PROMPTS[PostForm.title.state], reply_markup=stage_keyboard(0))


@router.message(CommandStart())
async def start(message: Message) -> None:
    if not allowed(message.from_user.id if message.from_user else None):
        await message.answer("Этот бот закрыт для этого аккаунта.")
        return
    await message.answer("Привет! Нажмите кнопку, чтобы собрать готовый пост.", reply_markup=main_keyboard())


@router.message(F.text == BTN_CREATE)
async def create(message: Message, state: FSMContext) -> None:
    if not allowed(message.from_user.id if message.from_user else None):
        await message.answer("Этот бот закрыт для этого аккаунта.")
        return
    await begin(message, state)


@router.message(F.text == BTN_CANCEL)
async def cancel(message: Message, state: FSMContext) -> None:
    await state.clear()
    await message.answer("Создание поста отменено.", reply_markup=main_keyboard())


@router.message(F.text == BTN_RESTART)
async def restart(message: Message, state: FSMContext) -> None:
    if not allowed(message.from_user.id if message.from_user else None):
        await message.answer("Этот бот закрыт для этого аккаунта.")
        return
    await begin(message, state)


@router.message(F.text == BTN_BACK)
async def back(message: Message, state: FSMContext) -> None:
    current = await state.get_state()
    try:
        index = next(i for i, form_state in enumerate(FORM_STATES) if form_state.state == current)
    except StopIteration:
        await message.answer("Сейчас нет шага, к которому можно вернуться.", reply_markup=main_keyboard())
        return
    if index == 0:
        await message.answer("Вы уже на первом шаге.", reply_markup=stage_keyboard(0))
        return
    previous = FORM_STATES[index - 1]
    await state.set_state(previous)
    await message.answer(
        f"Шаг {index} из 6. {PROMPTS[previous.state]}",
        reply_markup=stage_keyboard(index - 1),
    )


async def accept_text(message: Message, state: FSMContext, field: str, next_state: State, step_index: int) -> None:
    if not allowed(message.from_user.id if message.from_user else None):
        await message.answer("Этот бот закрыт для этого аккаунта.")
        return
    text = (message.text or "").strip()
    if not text or text.startswith("/"):
        await message.answer("Пришлите ответ текстом или воспользуйтесь кнопками ниже.", reply_markup=stage_keyboard(step_index))
        return
    await state.update_data(**{field: text})
    await state.set_state(next_state)
    await message.answer(
        f"Шаг {step_index + 2} из 6. {PROMPTS[next_state.state]}",
        reply_markup=stage_keyboard(step_index + 1),
    )


@router.message(PostForm.title, F.text)
async def title(message: Message, state: FSMContext) -> None:
    await accept_text(message, state, "title", PostForm.description, 0)


@router.message(PostForm.description, F.text)
async def description(message: Message, state: FSMContext) -> None:
    await accept_text(message, state, "description", PostForm.tags, 1)


@router.message(PostForm.tags, F.text)
async def tags(message: Message, state: FSMContext) -> None:
    await accept_text(message, state, "tags", PostForm.version, 2)


@router.message(PostForm.version, F.text)
async def version(message: Message, state: FSMContext) -> None:
    await accept_text(message, state, "version", PostForm.mod, 3)


@router.message(PostForm.mod, F.text)
async def mod(message: Message, state: FSMContext) -> None:
    await accept_text(message, state, "mod", PostForm.photo, 4)


@router.message(PostForm.photo, F.photo)
async def photo(message: Message, state: FSMContext) -> None:
    if not allowed(message.from_user.id if message.from_user else None):
        await message.answer("Этот бот закрыт для этого аккаунта.")
        return
    data = await state.get_data()
    data["photo"] = message.photo[-1].file_id
    token = secrets.token_urlsafe(8)
    ready_posts[token] = data
    while len(ready_posts) > 100:
        ready_posts.pop(next(iter(ready_posts)))

    await message.answer_photo(
        photo=data["photo"],
        caption=format_post(data),
        show_caption_above_media=True,
        reply_markup=share_keyboard(token),
    )
    await state.clear()
    await message.answer("Пост готов: текст и картинка в одном сообщении.", reply_markup=main_keyboard())


@router.message(PostForm.photo)
async def wrong_photo(message: Message) -> None:
    await message.answer("Пришлите картинку как фото или воспользуйтесь кнопками ниже.", reply_markup=stage_keyboard(5))


@router.inline_query()
async def inline_share(query: InlineQuery) -> None:
    if not allowed(query.from_user.id):
        await query.answer([], cache_time=0, is_personal=True)
        return
    post = ready_posts.get(query.query.strip())
    results: list[Any] = []
    if post:
        results.append(InlineQueryResultCachedPhoto(
            id=query.query.strip(),
            photo_file_id=post["photo"],
            title=post["title"][:50],
            caption=format_post(post),
            parse_mode=ParseMode.HTML,
            show_caption_above_media=True,
        ))
    await query.answer(results, cache_time=0, is_personal=True)


async def main() -> None:
    if not TOKEN:
        raise SystemExit("Укажите TELEGRAM_BOT_TOKEN в .env или переменных окружения.")
    if not ALLOWED_USER_IDS:
        raise SystemExit("Укажите свой Telegram ID в ALLOWED_USER_IDS.")
    bot = Bot(TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
