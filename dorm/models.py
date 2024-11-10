from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import re

from django.contrib.auth.hashers import make_password



class Region(models.Model):
    region_name = models.CharField(max_length=100, verbose_name="Область")


    def __str__(self):
        return f"{self.region_name}"


class UserManager(BaseUserManager):
    def create_user(self, s, password=None, **extra_fields):
        if not s:
            raise ValueError('Users must have an "s" field')

        s = s.upper()
        user = self.model(s=s, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, s, password=None, **extra_fields):
        s = s.upper()
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)

        if extra_fields.get('is_staff') is not True:
            raise ValueError('Superuser must have is_staff=True.')
        if extra_fields.get('is_superuser') is not True:
            raise ValueError('Superuser must have is_superuser=True.')

        if not re.fullmatch(r"F\d{8}", s):
            raise ValueError(
                'Superuser "s" must start with "F" followed by exactly eight digits, making it 9 characters long.')

        return self.create_user(s, password, **extra_fields)

class User(AbstractBaseUser, PermissionsMixin):
    s = models.CharField(max_length=100, unique=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    middle_name = models.CharField(max_length=100, verbose_name="Отчество", blank=True, null=True)
    email = models.EmailField(blank=True)
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 's'
    REQUIRED_FIELDS = []

    def __str__(self):
        return self.s

    def save(self, *args, **kwargs):
        if self.password and not self.password.startswith('pbkdf2_sha256$'):
            self.set_password(self.password)
        if self.s:
            self.s = self.s.upper()
        super().save(*args, **kwargs)

class Student(User):
    course = models.CharField(max_length=100)
    region = models.ForeignKey('Region', on_delete=models.CASCADE, verbose_name="Область")

    class Meta:
        verbose_name = 'Student'
        verbose_name_plural = 'Students'

    def save(self, *args, **kwargs):
        if not re.fullmatch(r"S\d{8}", self.s):
            raise ValueError(
                'Student "s" must start with "S" followed by exactly eight digits, making it 9 characters long.')
        super().save(*args, **kwargs)

class Admin(User):
    department = models.CharField(max_length=100)

    class Meta:
        verbose_name = 'Admin'
        verbose_name_plural = 'Admins'
        permissions = [
            ('can_manage_students', 'Can manage students'),
        ]

    def save(self, *args, **kwargs):
        if not re.fullmatch(r"F\d{8}", self.s):
            raise ValueError(
                'Admin "s" must start with "F" followed by exactly eight digits, making it 9 characters long.')
        super().save(*args, **kwargs)



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
    question_type = models.CharField(max_length=50, choices=QUESTION_TYPE_CHOICES, verbose_name="Тип вопроса")

    def __str__(self):
        return self.question_text



class Application(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name="Студент", related_name="application")
    approval = models.BooleanField(default=False, verbose_name="Одобрение")
    dormitory_choice = models.ForeignKey(Dorm, on_delete=models.SET_NULL, null=True, default=None, verbose_name="Выбор общежития")
    test_answers = models.JSONField(default=dict, verbose_name="Ответы теста")
    test_result = models.CharField(max_length=1, null=True, blank=True, verbose_name="Результат теста")
    payment_screenshot = models.ImageField(upload_to='payments/', null=True, blank=True, verbose_name="Скрин оплаты")
    priority = models.ImageField(upload_to='priority/', null=True, blank=True, verbose_name="Справка")

    def __str__(self):
        return f"Заявка от {self.student}"




class QuestionAnswer(models.Model):
    question = models.CharField(max_length=255)
    answer = models.TextField()

    def __str__(self):
        return self.question




class StudentInDorm(models.Model):
    student_id = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name="student", related_name="Студент")
    dorm_id = models.ForeignKey(Dorm, on_delete=models.CASCADE, verbose_name="dorm", related_name="Общежитие")
    room = models.CharField(max_length=10, null=True, blank=True, verbose_name="Комната")
    application_id = models.ForeignKey(Application, on_delete=models.CASCADE, verbose_name="application", related_name="Заявление")
    order = models.ImageField(upload_to='orders/', null=True, blank=True, verbose_name="Ордер")

    def __str__(self):
        return f"{self.student_id}"