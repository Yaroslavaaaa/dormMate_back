# Используем образ Python 3.9 (или другую версию, которая совместима)
FROM python:3.9-slim

# Установим pip
RUN pip install --upgrade pip

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости, избегая кеширования
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код проекта в контейнер
COPY . /app

# Устанавливаем рабочую директорию
WORKDIR /app

# Запуск приложения (пример для Django)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
