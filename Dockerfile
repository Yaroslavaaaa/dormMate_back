# Используем Python 3.10
FROM python:3.10-slim

# Обновляем pip
RUN pip install --upgrade pip

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости, избегая кеширования
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код проекта
COPY . /app

# Устанавливаем рабочую директорию
WORKDIR /app

# Запуск приложения (например, для Django)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
