import os
import sys
import logging
from datetime import datetime, time as dt_time
from zoneinfo import ZoneInfo

from dotenv import load_dotenv
from telegram import Update
from telegram.ext import Application, ApplicationBuilder, CommandHandler, ContextTypes, Defaults

# ── Загрузка .env (BOT_TOKEN, NOTIFY_TIME, ALLOWED_USER_IDS, USER_BIRTH_DATES) ─
load_dotenv()
TOKEN = os.getenv("BOT_TOKEN")
raw_notify = os.getenv("NOTIFY_TIME")
notify_display = raw_notify
raw_allowed = os.getenv("ALLOWED_USER_IDS", "").strip()
raw_births = os.getenv("USER_BIRTH_DATES", "").strip()

if not TOKEN or not raw_notify or not raw_allowed or not raw_births:
    logging.error(
        "Missing BOT_TOKEN, NOTIFY_TIME, ALLOWED_USER_IDS or USER_BIRTH_DATES in environment."
    )
    sys.exit(1)

try:
    ALLOWED_USER_IDS = frozenset(
        int(x.strip())
        for x in raw_allowed.replace(" ", "").split(",")
        if x.strip()
    )
except ValueError as e:
    logging.error("Invalid ALLOWED_USER_IDS (comma-separated integers): %s", e)
    sys.exit(1)

if not ALLOWED_USER_IDS:
    logging.error("ALLOWED_USER_IDS is empty.")
    sys.exit(1)

# ── Логирование и часовой пояс ────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO)
MSK = ZoneInfo("Europe/Moscow")


def _parse_user_birth_map(raw: str) -> dict[int, datetime]:
    """Формат: «id:YYYY-MM-DD HH:MM|id2:...» — разделитель записей |."""
    out: dict[int, datetime] = {}
    for entry in raw.split("|"):
        entry = entry.strip()
        if not entry:
            continue
        if ":" not in entry:
            raise ValueError(f"Ожидалось id:дата, получено: {entry!r}")
        uid_str, rest = entry.split(":", 1)
        uid = int(uid_str.strip())
        dt = datetime.strptime(rest.strip(), "%Y-%m-%d %H:%M").replace(tzinfo=MSK)
        out[uid] = dt
    return out


try:
    BIRTH_BY_USER = _parse_user_birth_map(raw_births)
except ValueError as e:
    logging.error("Invalid USER_BIRTH_DATES: %s", e)
    sys.exit(1)

_ids_birth = frozenset(BIRTH_BY_USER.keys())
if _ids_birth != ALLOWED_USER_IDS:
    logging.error(
        "ALLOWED_USER_IDS и USER_BIRTH_DATES должны содержать одни и те же id. "
        "allowed=%s birth=%s",
        sorted(ALLOWED_USER_IDS),
        sorted(_ids_birth),
    )
    sys.exit(1)

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


def user_allowed(update: Update) -> bool:
    u = update.effective_user
    return u is not None and u.id in ALLOWED_USER_IDS


async def deny_if_not_allowed(update: Update) -> bool:
    """Возвращает True, если нужно прервать обработчик (пользователь не в белом списке)."""
    if user_allowed(update):
        return False
    if update.message:
        await update.message.reply_text("❌ Доступ запрещён.")
    logging.warning("Denied access: user_id=%s", getattr(update.effective_user, "id", None))
    return True

# ── Статистика жизни ───────────────────────────────────────────────────────────
def calc_life_stats(birth_dt: datetime, now: datetime):
    delta = now - birth_dt
    days = delta.days
    weeks = days // 7
    months = int(days / 30.4375)
    years = int(days / 365.2425)
    return days, weeks, months, years

# ── Команда /start ─────────────────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_not_allowed(update):
        return

    uid = update.effective_user.id
    birth_dt = BIRTH_BY_USER.get(uid)
    if not birth_dt:
        return

    days, weeks, months, years = calc_life_stats(birth_dt, datetime.now(tz=MSK))
    await update.message.reply_text(
        f"✅ Бот активен. Дата рождения из конфига: {birth_dt.strftime('%Y-%m-%d %H:%M')} МСК.\n"
        f"Сейчас: {days}-й день ({weeks}-я неделя, {months}-й месяц, {years}-й год).\n"
        f"Уведомления каждый день в {notify_display} МСК."
    )

# ── Команда /info ──────────────────────────────────────────────────────────────
async def cmd_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_not_allowed(update):
        return
    if update.effective_user.id not in BIRTH_BY_USER:
        return
    await send_stats(update, context)

# ── Команда /help ──────────────────────────────────────────────────────────────
async def cmd_help(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_not_allowed(update):
        return
    help_text = (
        "📋 Доступные команды:\n"
        "/start — приветствие и сводка (дата рождения задаётся в конфиге)\n"
        "/info — текущая статистика\n"
        "/test — тестовое уведомление\n"
        "/help — это сообщение"
    )
    await update.message.reply_text(help_text)

# ── Команда /test ──────────────────────────────────────────────────────────────
async def cmd_test(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if await deny_if_not_allowed(update):
        return
    birth_dt = BIRTH_BY_USER.get(update.effective_user.id)
    if not birth_dt:
        return
    days, weeks, months, years = calc_life_stats(birth_dt, datetime.now(tz=MSK))
    msg = (
        "🛠 Тестовое уведомление!\n"
        f"{days}-й день жизни ({weeks}-я неделя, {months}-й месяц, {years}-й год)."
    )
    await update.message.reply_text(msg)

# ── Вспомогательная отправка статистики ───────────────────────────────────────
async def send_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    birth_dt = BIRTH_BY_USER[update.effective_user.id]
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

async def post_init(application: Application) -> None:
    jq = application.job_queue
    if jq is None:
        logging.error("Job queue is not available.")
        return
    for uid, birth_dt in BIRTH_BY_USER.items():
        job_name = f"daily_{uid}"
        for job in jq.get_jobs_by_name(job_name):
            job.schedule_removal()
        job = jq.run_daily(
            daily_job,
            time=notify_time,
            data={"chat_id": uid, "birth_dt": birth_dt},
            name=job_name,
        )
        logging.info(
            "Daily job scheduled: user_id=%s next_run=%s",
            uid,
            getattr(job, "next_t", None),
        )


# ── Точка входа ───────────────────────────────────────────────────────────────
if __name__ == "__main__":
    defaults = Defaults(tzinfo=MSK)
    app = (
        ApplicationBuilder()
        .token(TOKEN)
        .defaults(defaults)
        .post_init(post_init)
        .build()
    )
    app.add_handler(CommandHandler("start", cmd_start))
    app.add_handler(CommandHandler("info", cmd_info))
    app.add_handler(CommandHandler("help", cmd_help))
    app.add_handler(CommandHandler("test", cmd_test))
    app.run_polling()
