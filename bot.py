import os
import logging
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    ContextTypes,
)

# ── Инициализация и логирование ─────────────────────────────────────────────
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
logging.basicConfig(level=logging.INFO)

# ── Функция расчёта статистики ───────────────────────────────────────────────
def calc_life_stats(birth_dt: datetime, now: datetime):
    delta = now - birth_dt
    days = delta.days
    weeks = days // 7
    months = int(days / 30.4375)
    years = int(days / 365.2425)
    return days, weeks, months, years

# ── Обработчики команд ───────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Приветствие и совет установить дату рождения
    if 'birth_dt' not in context.user_data:
        await update.message.reply_text(
            "Привет! Пожалуйста, задайте дату рождения командой:
"            "/setbirth YYYY-MM-DD HH:MM"
            )
        return

    birth_dt: datetime = context.user_data['birth_dt']
    now = datetime.now(tz=birth_dt.tzinfo)
    days, weeks, months, years = calc_life_stats(birth_dt, now)

    msg = (
        f"Привет!
"
        f"Сегодня {days}-й день жизни ({weeks}-я неделя, {months}-й месяц, {years}-й год)."
    )
    await update.message.reply_text(msg)


async def set_birth(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Установка даты рождения пользователем
    args = context.args
    if not args:
        await update.message.reply_text(
            "Использование: /setbirth YYYY-MM-DD HH:MM"
        )
        return

    text = ' '.join(args)
    try:
        birth_dt = datetime.strptime(text, "%Y-%m-%d %H:%M").replace(
            tzinfo=timezone(timedelta(hours=3))  # МСК
        )
    except ValueError:
        await update.message.reply_text(
            "Неправильный формат даты. Пример: /setbirth 1990-01-15 08:30"
        )
        return

    # Сохраняем в user_data и планируем ежедневные уведомления
    context.user_data['birth_dt'] = birth_dt
    chat_id = update.effective_chat.id
    context.job_queue.run_daily(
        daily_job,
        time=birth_dt.timetz().replace(hour=10, minute=0),
        data={'chat_id': chat_id, 'birth_dt': birth_dt},
        name=f"daily_{chat_id}",
    )

    await update.message.reply_text(
        f"Дата рождения установлена: {birth_dt.strftime('%Y-%m-%d %H:%M')} МСК."
        "\nУведомления будут приходить каждый день в 10:00 МСК."
    )


async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    # Ежедневное сообщение
    job_data = context.job.data
    chat_id = job_data['chat_id']
    birth_dt: datetime = job_data['birth_dt']
    now = datetime.now(tz=birth_dt.tzinfo)
    days, weeks, months, years = calc_life_stats(birth_dt, now)

    msg = (
        f"Ещё один день прожит!\n"
        f"{days}-й день жизни ({weeks}-я неделя, {months}-й месяц, {years}-й год)."
    )
    await context.bot.send_message(chat_id, msg)


# ── Запуск приложения ────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()

    # Обработчики
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("setbirth", set_birth))

    # Запуск polling
    app.run_polling()
