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

# Открываем порт 8080
EXPOSE 8080

# Запуск приложения (например, для Django на порту 8080)
CMD ["python", "manage.py", "runserver", "0.0.0.0:8080"]
