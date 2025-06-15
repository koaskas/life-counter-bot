import os
import logging
from datetime import datetime, timedelta, timezone

from dotenv import load_dotenv
from telegram.ext import Application, CommandHandler, ContextTypes

# ── базовая инициализация ────────────────────────────────────────────────────
load_dotenv()                          # читает переменные из .env
TOKEN = os.getenv("BOT_TOKEN")
BIRTH_RAW = os.getenv("BIRTH_DATETIME", "2000-01-01 00:00")
BIRTH_DT = datetime.strptime(BIRTH_RAW, "%Y-%m-%d %H:%M").replace(
    tzinfo=timezone(timedelta(hours=3))  # МСК
)

logging.basicConfig(level=logging.INFO)

# ── вспомогательная функция ──────────────────────────────────────────────────
def calc_life_stats(now: datetime):
    delta = now - BIRTH_DT
    days = delta.days
    weeks = days // 7
    months = int(days / 30.4375)        # среднее кол-во дней в месяце
    years = int(days / 365.2425)
    return days, weeks, months, years

# ── обработчики команд ───────────────────────────────────────────────────────
async def cmd_start(update, context):
    days, weeks, months, years = calc_life_stats(
        datetime.now(tz=timezone.utc).astimezone(BIRTH_DT.tzinfo)
    )
    msg = (
        f"Привет!\n"
        f"Сегодня {days}-й день, {weeks}-я неделя,\n"
        f"{months}-й месяц и {years}-й год твоей жизни."
    )
    await update.message.reply_text(msg)

async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    chat_id = context.job.data
    days, weeks, months, years = calc_life_stats(
        datetime.now(tz=timezone.utc).astimezone(BIRTH_DT.tzinfo)
    )
    txt = (
        f"Ещё один день прожит!\n"
        f"{days}-й день ({weeks}-я неделя, "
        f"{months}-й месяц, {years}-й год) твоей жизни."
    )
    await context.bot.send_message(chat_id, txt)

# ── запуск приложения ────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = Application.builder().token(TOKEN).build()

    # команда /start
    app.add_handler(CommandHandler("start", cmd_start))

    # ежедневная задача в 10:00 МСК; чат_id берём при первой /start
    # (по уму надо хранить chat_id в БД, но для начала так)
    async def set_alarm(update, context):
        chat_id = update.effective_chat.id
        context.job_queue.run_daily(
            daily_job,
            time=datetime.time(10, 0, tzinfo=BIRTH_DT.tzinfo),
            data=chat_id,
            name=str(chat_id),
        )
        await update.message.reply_text("Окей! Буду писать каждый день в 10:00.")

    app.add_handler(CommandHandler("alarm", set_alarm))

    app.run_polling()
