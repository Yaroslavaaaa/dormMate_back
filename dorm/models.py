from django.db import models
from django.contrib.auth.hashers import make_password



class Region(models.Model):
    region_name = models.CharField(max_length=100, verbose_name="Область")


    def __str__(self):
        return f"{self.region_name}"

class Student(models.Model):
    student_s = models.CharField(max_length=100, verbose_name="S-ка студента")
    first_name = models.CharField(max_length=100, verbose_name="Имя")
    last_name = models.CharField(max_length=100, verbose_name="Фамилия")
    middle_name = models.CharField(max_length=100, verbose_name="Отчество", blank=True, null=True)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, verbose_name="Область")
    course = models.PositiveIntegerField(verbose_name="Курс")
    email = models.EmailField(verbose_name="Почта")
    password = models.CharField(max_length=128, verbose_name="Пароль")

    def save(self, *args, **kwargs):
        if not self.pk or not Student.objects.get(pk=self.pk).password == self.password:
            self.password = make_password(self.password)
        super(Student, self).save(*args, **kwargs)

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.student_s})"






class Dorm(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название")
    total_places = models.PositiveIntegerField(verbose_name="Количество мест")
    rooms_for_two = models.PositiveIntegerField(verbose_name="Количество комнат на 2")
    rooms_for_three = models.PositiveIntegerField(verbose_name="Количество комнат на 3")
    rooms_for_four = models.PositiveIntegerField(verbose_name="Количество комнат на 4")
    cost = models.PositiveIntegerField(verbose_name="Стоимость")

    def __str__(self):
        return self.name



class TestQuestion(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('psychological', 'Психологическая совместимость'),
        ('daily_routine', 'Режим дня'),
        ('habits', 'Вредные привычки'),
        ('values', 'Ценности'),
        ('household', 'Бытовые привычки'),
    ]

    question_text = models.TextField(verbose_name="Вопрос")
    answer_variant_a = models.TextField(verbose_name="Вариант a", default=None)
    answer_variant_b = models.TextField(verbose_name="Вариант b", default=None)
    answer_variant_c = models.TextField(verbose_name="Вариант c", default=None)
    answer_variant_d = models.TextField(verbose_name="Вариант d", default=None)
    question_type = models.CharField(max_length=50, choices=QUESTION_TYPE_CHOICES, verbose_name="Тип вопроса")

    def __str__(self):
        return self.question_text



class Application(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name="Студент", related_name="applications")
    approval = models.BooleanField(default=False, verbose_name="Одобрение")
    dormitory_choice = models.ForeignKey(Dorm, on_delete=models.SET_NULL, null=True, default=None, verbose_name="Выбор общежития")
    test_answers = models.JSONField(default=dict, verbose_name="Ответы теста")
    test_result = models.CharField(max_length=1, null=True, blank=True, verbose_name="Результат теста")
    payment_screenshot = models.ImageField(upload_to='payments/', null=True, blank=True, verbose_name="Скрин оплаты")

    def __str__(self):
        return f"Заявка от {self.student}"




class QuestionAnswer(models.Model):
    question = models.CharField(max_length=255)
    answer = models.TextField()

    def __str__(self):
        return self.question