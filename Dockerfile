# ─────────────────────────────────────────────────────────────
# Life-Counter-Bot — образ для продакшен-контейнера
# ─────────────────────────────────────────────────────────────
FROM python:3.12-slim

# 1. Устанавливаем системные зависимости
RUN apt-get update && apt-get install -y --no-install-recommends \
        tzdata \
    && rm -rf /var/lib/apt/lists/*

# 2. Работаем от непривилегированного пользователя
RUN useradd -ms /bin/bash botuser
USER botuser
WORKDIR /app

# 3. Копируем зависимости и устанавливаем их отдельно
COPY --chown=botuser:botuser requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 4. Копируем оставшийся исходный код
COPY --chown=botuser:botuser . .

# 5. Значение TZ можно пробросить через docker-compose
ENV PYTHONUNBUFFERED=1

# 6. Команда по умолчанию
CMD ["python", "-u", "bot.py"]