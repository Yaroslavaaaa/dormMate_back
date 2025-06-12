# Используем Python 3.9 (или Python 3.10) вместо Python 3.11
FROM python:3.9-slim

# Устанавливаем pip и обновляем его
RUN pip install --upgrade pip

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости, избегая кеширования
# Включаем установку зависимостей только для Linux (исключаем pywin32)
RUN sed -i '/pywin32/d' requirements.txt && \
    pip install --no-cache-dir -r requirements.txt

# Копируем код проекта в контейнер
COPY . /app

# Устанавливаем рабочую директорию
WORKDIR /app

# Запуск приложения (например, для Django)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
