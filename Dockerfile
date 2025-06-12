# Используем Python 3.10 или более новую версию
FROM python:3.11-slim

# Устанавливаем pip и обновляем его
RUN pip install --upgrade pip

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости, избегая кеширования
RUN pip install --no-cache-dir -r requirements.txt

# Копируем исходный код
COPY . /app

# Устанавливаем рабочую директорию
WORKDIR /app

# Запуск приложения (например, Django)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
