# 1. Базовый образ Python
FROM python:3.11-slim

# 2. Установка системных зависимостей (при необходимости)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# 3. Установка рабочей директории
WORKDIR /app

# 4. Копирование зависимостей
COPY requirements.txt .

# 5. Установка Python-зависимостей
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# 6. Копирование исходного кода проекта
COPY . .

# 7. EXPOSE: Для локальной отладки (Cloud Run игнорирует)
EXPOSE 8080

# 8. Команда запуска:
#   - Важно: слушаем порт 8080 (Cloud Run ждёт именно его!)
CMD ["gunicorn", "dormMate.wsgi:application", "--bind", "0.0.0.0:8080"]
