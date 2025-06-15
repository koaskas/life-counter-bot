import os
import logging
from datetime import datetime, timedelta, timezone, time as dt_time

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# ── Инициализация и логирование ─────────────────────────────────────────────
token = os.getenv("BOT_TOKEN")
logging.basicConfig(level=logging.INFO)

# Московский часовой пояс
MSK = timezone(timedelta(hours=3))

# ── Функция расчёта статистики ───────────────────────────────────────────────
def calc_life_stats(birth_dt: datetime, now: datetime):
    delta = now - birth_dt
    days = delta.days
    weeks = days // 7
    months = int(days / 30.4375)
    years = int(days / 365.2425)
    return days, weeks, months, years

# ── Обработчик команды /start ─────────────────────────────────────────────────
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    chat_id = update.effective_chat.id

    # Если переданы аргументы — задаём/обновляем дату рождения
    if args:
        text = ' '.join(args)
        try:
            birth_dt = datetime.strptime(text, "%Y-%m-%d %H:%M").replace(tzinfo=MSK)
        except ValueError:
            await update.message.reply_text(
                "Неправильный формат. Используй: /start YYYY-MM-DD HH:MM (МСК)"
            )
            return

        # Сохраняем дату и перезапускаем задачу
        context.user_data['birth_dt'] = birth_dt
        job_name = f"daily_{chat_id}"
        # удаляем старую задачу, если есть
        for job in context.job_queue.get_jobs_by_name(job_name):
            job.schedule_removal()
        # планируем ежедневное сообщение в 10:00 МСК
        context.job_queue.run_daily(
            daily_job,
            time=dt_time(10, 0, tzinfo=MSK),
            data={'chat_id': chat_id, 'birth_dt': birth_dt},
            name=job_name,
        )
        # Немедленный расчёт и ответ
        days, weeks, months, years = calc_life_stats(birth_dt, datetime.now(tz=MSK))
        await update.message.reply_text(
            f"Дата рождения установлена: {birth_dt.strftime('%Y-%m-%d %H:%M')} МСК."
            f"\nБуду писать каждый день в 10:00 МСК."  
            f"\nСейчас: {days}-й день ({weeks}-я неделя, {months}-й месяц, {years}-й год)."
        )
        return

    # Если аргументов нет
    if 'birth_dt' not in context.user_data:
        await update.message.reply_text(
            "Привет! Чтобы начать, укажи дату рождения:
"            "/start YYYY-MM-DD HH:MM (МСК)"
        )
        return

    # Без аргументов, но дата уже есть — просто выводим обновлённую статистику
    birth_dt = context.user_data['birth_dt']
    days, weeks, months, years = calc_life_stats(birth_dt, datetime.now(tz=MSK))
    await update.message.reply_text(
        f"Текущая статистика:\n"
        f"{days}-й день жизни ({weeks}-я неделя, {months}-й месяц, {years}-й год)."
    )


# ── Ежедневное уведомление ────────────────────────────────────────────────────
async def daily_job(context: ContextTypes.DEFAULT_TYPE):
    data = context.job.data
    chat_id = data['chat_id']
    birth_dt: datetime = data['birth_dt']
    now = datetime.now(tz=MSK)
    days, weeks, months, years = calc_life_stats(birth_dt, now)
    msg = (
        f"Ещё один день!"
        f"\n{days}-й день жизни ({weeks}-я неделя, {months}-й месяц, {years}-й год)."
    )
    await context.bot.send_message(chat_id, msg)


# ── Запуск бота ────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    app = Application.builder().token(token).build()
    app.add_handler(CommandHandler("start", cmd_start))
    app.run_polling()
