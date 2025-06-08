# Используем официальный образ Python как базовый
FROM python:3.11-slim

# Установка зависимостей
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

# Открываем порт 8000
EXPOSE 8000

# Статические файлы (если нужно)
# ENV DJANGO_SETTINGS_MODULE=dormMate.settings
# RUN python manage.py collectstatic --noinput

# Запуск через gunicorn (замени 'dormMate' на свою папку с settings)
CMD ["gunicorn", "dormMate.wsgi:application", "--bind", "0.0.0.0:8000"]
