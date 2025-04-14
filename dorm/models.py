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

        if not password and 'birth_date' in extra_fields:
            password = extra_fields['birth_date'].strftime('%d%m%Y')

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
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]

    s = models.CharField(max_length=100, unique=True, null=True)
    first_name = models.CharField(max_length=30, blank=True)
    last_name = models.CharField(max_length=30, blank=True)
    middle_name = models.CharField(max_length=100, verbose_name="Отчество", blank=True, null=True)
    email = models.EmailField(blank=True)
    birth_date = models.DateField(verbose_name="Дата рождения", blank=True, null=True)
    phone_number = models.CharField(max_length=11, blank=True, null=True)
    avatar = models.ImageField(blank=True, default='avatar/no-avatar.png')
    gender = models.CharField(
        max_length=1,
        choices=GENDER_CHOICES,
        verbose_name="Пол",
        blank=True,
        null=True
    )
    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    objects = UserManager()

    USERNAME_FIELD = 's'
    REQUIRED_FIELDS = []

    def __str__(self):
        return f"{self.first_name} {self.last_name} {self.middle_name}"

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


class DormImage(models.Model):
    dorm = models.ForeignKey(Dorm, related_name="images", on_delete=models.CASCADE)
    image = models.ImageField(upload_to="dorm_images/", verbose_name="Фото")

    def __str__(self):
        return f"Фото для {self.dorm.name}"



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



class Keyword(models.Model):
    keyword = models.CharField(max_length=100, verbose_name="Ключевое слово")

    def __str__(self):
        return self.keyword

class EvidenceType(models.Model):
    DATA_TYPE_CHOICES = [
        ('file', 'Файл'),
        ('numeric', 'Числовое значение'),
    ]
    name = models.CharField(max_length=100, verbose_name="Название")
    code = models.CharField(max_length=50, unique=True, verbose_name="Код")
    priority = models.IntegerField(
        default=0,
        help_text="Чем больше число, тем выше приоритет",
        verbose_name="Приоритет"
    )
    data_type = models.CharField(max_length=20, choices=DATA_TYPE_CHOICES, verbose_name="Тип данных")
    auto_fill_field = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Название поля в Application или Student, откуда брать значение при отсутствии загруженного доказательства",
        verbose_name="Поле автозаполнения"
    )
    # ManyToManyField через промежуточную модель EvidenceKeyword
    keywords = models.ManyToManyField('Keyword', through='EvidenceKeyword', blank=True, verbose_name="Ключевые слова")

    def __str__(self):
        return self.name









class EvidenceKeyword(models.Model):
    evidence_type = models.ForeignKey(
        EvidenceType,
        on_delete=models.CASCADE,
        related_name='evidence_keywords',
        related_query_name='evidence_keyword'  # Изменённое обратное имя для запросов
    )
    keyword = models.ForeignKey(
        Keyword,
        on_delete=models.CASCADE,
        related_name='evidence_keywords'
    )

    def __str__(self):
        return f"{self.evidence_type.name} - {self.keyword.keyword}"



class Application(models.Model):
    STATUS_CHOICES = [
        ('pending', 'На рассмотрении'),
        ('approved', 'Одобрено'),
        ('rejected', 'Отклонено'),
        ('awaiting_payment', 'Ожидание оплаты'),
        ('awaiting_order', 'Ожидание ордера'),
        ('order', 'Ордер получен'),
    ]
    student = models.OneToOneField(
        Student, on_delete=models.CASCADE,
        verbose_name="Студент", related_name="application"
    )
    approval = models.BooleanField(default=False, verbose_name="Одобрение")
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='pending', verbose_name="Статус")
    dormitory_cost = models.PositiveIntegerField(verbose_name="Выбранная стоимость проживания")
    test_answers = models.JSONField(default=dict, verbose_name="Ответы теста")
    test_result = models.CharField(max_length=1, null=True, blank=True, verbose_name="Результат теста")
    payment_screenshot = models.FileField(upload_to='payments/', null=True, blank=True, verbose_name="Скрин оплаты")
    is_full_payment = models.BooleanField(null=True, blank=True, verbose_name="Полная оплата")

    # Поля для ЕНТ и GPA остаются в модели
    ent_result = models.PositiveIntegerField(null=True, blank=True, verbose_name="Результат ЕНТ")
    gpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, verbose_name="GPA")

    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Время последнего обновления")


    def __str__(self):
        return f"Заявка от {self.student}"





class ApplicationEvidence(models.Model):
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE, related_name='evidences',
        verbose_name="Заявка"
    )
    evidence_type = models.ForeignKey(
        EvidenceType, on_delete=models.CASCADE, verbose_name="Тип доказательства"
    )
    file = models.FileField(upload_to='evidences/', null=True, blank=True, verbose_name="Файл доказательства")
    numeric_value = models.DecimalField(
        max_digits=6, decimal_places=2, null=True, blank=True,
        verbose_name="Числовое значение"
    )
    approved = models.BooleanField(
        null=True, blank=True,
        verbose_name="Одобрено",
        help_text="Если True – справка одобрена, если False – отклонена, если None – не проверена"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время создания")

    def __str__(self):
        return f"{self.application.id} - {self.evidence_type.name}"





class Chat(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chats')
    status = models.CharField(max_length=30, default='waiting_for_admin')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Chat {self.id} - {self.student}"

class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages', null=True, blank=True)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.sender} -> {self.receiver}: {self.content}"

class Notification(models.Model):
    # Если уведомления создаются для пользователя (админа или студента)
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification for {self.recipient} at {self.created_at}"

class QuestionAnswer(models.Model):
    question = models.TextField(unique=True)
    answer = models.TextField()

    def __str__(self):
        return f"Q: {self.question} A: {self.answer}"


class StudentInDorm(models.Model):
    student_id = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name="student", related_name="Студент")
    dorm_id = models.ForeignKey(Dorm, on_delete=models.CASCADE, verbose_name="dorm", related_name="Общежитие", null=True)
    group = models.IntegerField(max_length=10, null=True, blank=True, verbose_name="Группа")
    application_id = models.ForeignKey(Application, on_delete=models.CASCADE, verbose_name="application", related_name="Заявление")
    order = models.ImageField(upload_to='orders/', null=True, blank=True, verbose_name="Ордер")
    room = models.CharField(max_length=10, null=True, blank=True, verbose_name="Комната")

    def __str__(self):
        return f"{self.student_id}"




