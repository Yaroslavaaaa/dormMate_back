# Используем официальный образ Python как базовый
FROM python:3.11-slim

# Установка зависимостей для сборки и системных библиотек (опционально можно добавить gcc и др.)
RUN apt-get update && apt-get install -y \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию внутри контейнера
WORKDIR /app

# Копируем зависимости
COPY requirements.txt .

# Устанавливаем зависимости Python
RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Копируем всё приложение
COPY . .

# Открываем порт 8000 для Django
EXPOSE 8000

# Команда запуска (можешь поменять на gunicorn, если нужно)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
