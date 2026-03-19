import os
import sys
import logging
from datetime import datetime, timedelta, timezone, time as dt_time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, Defaults

# ── Загрузка .env и проверка переменных ───────────────────────────────────────
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
SECRET_KEY = os.getenv("BOT_KEY")
raw_notify = os.getenv("NOTIFY_TIME")
notify_display = raw_notify

if not TOKEN or not SECRET_KEY or not raw_notify:
    logging.error("Missing BOT_TOKEN, BOT_KEY or NOTIFY_TIME in environment.")
    sys.exit(1)

# ── Логирование и часовой пояс ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
MSK = ZoneInfo("Europe/Moscow")

# ── Парсинг времени уведомлений ───────────────────────────────────────────────
try:
    # Бывает, что значение в .env приходит в кавычках: NOTIFY_TIME="09:00"
    # dotenv обычно убирает кавычки, но сделаем парсинг устойчивым.
    cleaned = raw_notify.strip().strip('"').strip("'")
    notify_display = cleaned
    hour, minute = map(int, cleaned.split(':'))
    notify_time = dt_time(hour, minute, tzinfo=MSK)
except Exception as e:
    logging.error(f"Invalid NOTIFY_TIME format: {e}")
    sys.exit(1)

logging.info(
    "Daily notification configured: raw=%r parsed=%02d:%02d tz=%s",
    raw_notify,
    hour,
    minute,
    getattr(MSK, "key", str(MSK)),
)

# ── Статистика жизни ───────────────────────────────────────────────────────────
def calc_life_stats(birth_dt: datetime, now: datetime):
    delta = now - birth_dt
    days = delta.days
    weeks = days // 7
    months = int(days / 30.4375)
    years = int(days / 365.2425)
    return days, weeks, months, years

# ── Парсинг даты рождения ───────────────────────────────────────────────────────
def parse_birth(args):
    raw = ' '.join(args).replace("(МСК)", "").strip()
    return datetime.strptime(raw, "%Y-%m-%d %H:%M").replace(tzinfo=MSK)

# ── Команда /start ─────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    chat_id = update.effective_chat.id

    if len(args) < 3:
        await update.message.reply_text(
            "❌ Использование: /start <KEY> YYYY-MM-DD HH:MM (МСК)"
        )
        return

    key, *date_args = args
    if key != SECRET_KEY:
        await update.message.reply_text("❌ Неверный ключ доступа.")
        return

    try:
        birth_dt = parse_birth(date_args)
    except ValueError:
        await update.message.reply_text(
            "❌ Неправильный формат даты. Используй: /start <KEY> YYYY-MM-DD HH:MM"
        )
        return

    context.user_data['birth_dt'] = birth_dt
    job_name = f"daily_{chat_id}"
    for job in context.job_queue.get_jobs_by_name(job_name):
        job.schedule_removal()
    job = context.job_queue.run_daily(
        daily_job,
        time=notify_time,
        data={'chat_id': chat_id, 'birth_dt': birth_dt},
        name=job_name,
    )
    logging.info("Daily job scheduled: chat_id=%s next_run=%s", chat_id, getattr(job, "next_t", None))

    days, weeks, months, years = calc_life_stats(birth_dt, datetime.now(tz=MSK))
    await update.message.reply_text(
        f"✅ Дата рождения установлена: {birth_dt.strftime('%Y-%m-%d %H:%M')} МСК.\n"
        f"Сейчас: {days}-й день ({weeks}-я неделя, {months}-й месяц, {years}-й год).\n"
        f"Уведомления каждый день в {notify_display} МСК."
    )

# ── Команда /info ──────────────────────────────────────────────────────────────
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'birth_dt' not in context.user_data:
        await update.message.reply_text(
            "❌ Сначала укажи дату рождения: /start <KEY> YYYY-MM-DD HH:MM (МСК)"
        )
        return
    await send_stats(update, context)

# ── Команда /help ──────────────────────────────────────────────────────────────
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    help_text = (
        "📋 Доступные команды:\n"
        "/start <KEY> YYYY-MM-DD HH:MM (МСК) — задать дату рождения\n"
        "/info — получить текущую статистику\n"
        "/test — получить тестовое уведомление немедленно\n"
        "/help — показать это сообщение"
    )
    await update.message.reply_text(help_text)

# ── Команда /test ──────────────────────────────────────────────────────────────
async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if 'birth_dt' not in context.user_data:
        await update.message.reply_text(
            "❌ Сначала укажи дату рождения: /start <KEY> YYYY-MM-DD HH:MM (МСК)"
        )
        return
    birth_dt = context.user_data['birth_dt']
    days, weeks, months, years = calc_life_stats(birth_dt, datetime.now(tz=MSK))
    msg = (
        "🛠 Тестовое уведомление!\n"
        f"{days}-й день жизни ({weeks}-я неделя, {months}-й месяц, {years}-й год)."
    )
    await update.message.reply_text(msg)

# ── Вспомогательная отправка статистики ───────────────────────────────────────
async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birth_dt = context.user_data['birth_dt']
    now = datetime.now(tz=MSK)
    days, weeks, months, years = calc_life_stats(birth_dt, now)
    await update.message.reply_text(
        f"📊 Текущая статистика:\n"
        f"{days}-й день жизни ({weeks}-я неделя, {months}-й месяц, {years}-й год)."
    )

# ── Ежедневное уведомление ────────────────────────────────────────────────────
async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data['chat_id']
    birth_dt: datetime = data['birth_dt']
    now = datetime.now(tz=MSK)
    logging.info("Daily job triggered: chat_id=%s now=%s", chat_id, now.isoformat())
    days, weeks, months, years = calc_life_stats(birth_dt, now)
    msg = (
        f"⏰ Ещё один день жизни!\n"
        f"{days}-й день ({weeks}-я неделя, {months}-й месяц, {years}-й год)."
    )
    await context.bot.send_message(chat_id, msg)

# ── Точка входа ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    defaults = Defaults(tzinfo=MSK)
    app = ApplicationBuilder().token(TOKEN).defaults(defaults).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("test", cmd_test))
    app.run_polling()
