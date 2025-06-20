from django.db import models
from django.contrib.auth.models import AbstractBaseUser, BaseUserManager, PermissionsMixin
import re
from django.utils import timezone
from django.conf import settings
from auditlog.registry import auditlog
import os
import uuid
from azure.storage.blob import BlobServiceClient
from django.core.exceptions import ValidationError
from .storage_backends import AzureMediaStorage

from django.contrib.auth.hashers import make_password

import os, uuid


def avatar_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"avatars/temp_{uuid.uuid4().hex}{ext}"


def upload_to_dorm_image(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"dorm_images/temp_{uuid.uuid4().hex}{ext}"


def evidences_upload_path(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"evidences/temp_{uuid.uuid4().hex}{ext}"


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

        if not password:
            raise ValueError("Password must be provided.")

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
    phone_number = models.CharField(max_length=11, blank=True, unique=True)

    avatar = models.ImageField(upload_to=avatar_upload_path, default='avatars/no-avatar.png')
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
        return f"{self.first_name} {self.last_name} {self.middle_name or ''}".strip()

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_avatar_name = self.avatar.name

    def clean(self):
        super().clean()
        if self.s:
            if not re.fullmatch(r"S\d{8}|F\d{8}", self.s.upper()):
                raise ValidationError({'s': 'Должно быть "S" или "F" + 8 цифр.'})
            self.s = self.s.upper()

    def save(self, *args, **kwargs):
        if not self.password:
            raise ValueError("Password must be provided.")

        if not self.password.startswith('pbkdf2_sha256$'):
            self.set_password(self.password)

        is_new = self.pk is None
        super().save(*args, **kwargs)

        current_name = self.avatar.name
        if current_name == self._original_avatar_name:
            return

        if current_name == 'avatars/no-avatar.png':
            return

        file_obj = getattr(self.avatar, 'file', None)
        if not file_obj:
            return

        ext = os.path.splitext(current_name)[1].lower()
        unique_name = f"{uuid.uuid4().hex}{ext}"
        blob_path = f"avatars/user_{self.pk}/{unique_name}"

        file_obj.seek(0)
        data = file_obj.read()
        service = BlobServiceClient(
            account_url=f"https://{settings.AZURE_ACCOUNT_NAME}.blob.core.windows.net",
            credential=settings.AZURE_ACCOUNT_KEY
        )
        container = service.get_container_client(settings.AZURE_CONTAINER)
        container.get_blob_client(blob_path).upload_blob(data, overwrite=True)

        self.avatar.name = blob_path
        super().save(update_fields=['avatar'])

        self._original_avatar_name = self.avatar.name


class Student(User):
    course = models.CharField(max_length=100)
    region = models.ForeignKey('Region', on_delete=models.CASCADE, verbose_name="Область")
    gpa = models.DecimalField(max_digits=4, decimal_places=2, null=True, blank=True, verbose_name="GPA")
    iin = models.CharField(max_length=12, unique=True, blank=True, verbose_name="ИИН")

    class Meta:
        verbose_name = 'Student'
        verbose_name_plural = 'Students'

    def clean(self):
        super().clean()
        if self.s and not re.fullmatch(r"S\d{8}", self.s):
            raise ValidationError({'s': 'Должно быть "S" и ровно 8 цифр.'})

    def save(self, *args, **kwargs):
        if not self.password and self.birth_date:
            self.password = self.birth_date.strftime('%d%m%Y')

        if not self.password:
            raise ValueError("Password must be provided.")

        super().save(*args, **kwargs)


class Admin(User):
    ROLE_SUPER = 'SUPER'
    ROLE_OPERATOR = 'OP'
    ROLE_REQUEST = 'REQ'
    ROLE_COMMANDANT = 'COM'

    ROLE_CHOICES = [
        (ROLE_SUPER, 'Главный администратор'),
        (ROLE_OPERATOR, 'Оператор'),
        (ROLE_REQUEST, 'Администратор по работе с заявками'),
        (ROLE_COMMANDANT, 'Комендант')
    ]

    role = models.CharField(
        max_length=10,
        choices=ROLE_CHOICES,
        verbose_name="Роль администратора",
        default=ROLE_OPERATOR
    )

    class Meta:
        verbose_name = 'Admin'
        verbose_name_plural = 'Admins'
        permissions = [
            ('can_manage_students', 'Can manage students'),
        ]

    def clean(self):
        super().clean()
        if self.s and not re.fullmatch(r"F\d{8}", self.s):
            raise ValidationError({'s': 'Должно быть "F" и ровно 8 цифр.'})


import re
from django.db import models


class Dorm(models.Model):
    name_ru = models.CharField(max_length=255, verbose_name="Название (рус)")
    name_kk = models.CharField(max_length=255, blank=True, verbose_name="Атауы (қаз)")
    name_en = models.CharField(max_length=255, blank=True, verbose_name="Name (eng)")
    description_ru = models.TextField(blank=True, verbose_name="Описание (рус)")
    description_kk = models.TextField(blank=True, verbose_name="Сипаттамасы (қаз)")
    description_en = models.TextField(blank=True, verbose_name="Description (eng)")
    address = models.CharField(max_length=255, verbose_name="Адрес")
    total_places = models.PositiveIntegerField(verbose_name="Количество мест")
    cost = models.PositiveIntegerField(verbose_name="Стоимость")
    commandant = models.ForeignKey(
        Admin,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        verbose_name="Комендант"
    )

    def __str__(self):
        return self.name_ru

    def floors_count(self) -> int:
        return (
            self.rooms
            .values_list('floor', flat=True)
            .distinct()
            .count()
        )


class Room(models.Model):
    dorm = models.ForeignKey(
        Dorm,
        on_delete=models.CASCADE,
        related_name='rooms',
        verbose_name="Общежитие"
    )
    number = models.CharField(
        max_length=10,
        verbose_name="Номер комнаты",
        help_text="Например: 101, 101A, 202Б"
    )
    capacity = models.PositiveSmallIntegerField(
        verbose_name="Вместимость",
        help_text="2, 3 или 4"
    )

    floor = models.PositiveSmallIntegerField(
        verbose_name="Этаж",
        editable=False,
        default=0
    )

    class Meta:
        unique_together = ('dorm', 'number')
        ordering = ['dorm', 'number']

    def save(self, *args, **kwargs):

        match = re.match(r"^(\d+)", self.number)
        if match:
            num = int(match.group(1))
            self.floor = num // 100
        else:
            self.floor = 0
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.dorm.name_ru} — комн. {self.number} ({self.capacity}-мест.)"


class DormImage(models.Model):
    dorm = models.ForeignKey(Dorm, on_delete=models.CASCADE, related_name='images')
    image = models.ImageField(
        upload_to=upload_to_dorm_image,
        blank=True,
        null=True,
        storage=AzureMediaStorage()
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.image:
            self._original_image_name = self.image.name

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        file_obj = getattr(self.image, 'file', None)

        if self.image and (not hasattr(self, '_original_image_name') or self.image.name != self._original_image_name):
            ext = os.path.splitext(self.image.name)[1].lower()
            unique_name = f"{uuid.uuid4().hex}{ext}"
            blob_path = f"dorm_images/{unique_name}"

            file_obj.seek(0)
            data = file_obj.read()
            service = BlobServiceClient(
                account_url=f"https://{settings.AZURE_ACCOUNT_NAME}.blob.core.windows.net",
                credential=settings.AZURE_ACCOUNT_KEY
            )
            container = service.get_container_client(settings.AZURE_CONTAINER)
            container.get_blob_client(blob_path).upload_blob(data, overwrite=True)

            self.image.name = blob_path

        super().save(*args, **kwargs)

        if self.image:
            self._original_image_name = self.image.name


class TestQuestion(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('psychological', 'Психологическая совместимость'),
        ('daily_routine', 'Режим дня'),
        ('habits', 'Вредные привычки'),
        ('values', 'Ценности'),
        ('household', 'Бытовые привычки'),
    ]

    question_text_ru = models.TextField(blank=True, verbose_name="Вопрос (рус)", default="")
    question_text_kk = models.TextField(blank=True, verbose_name="Сұрақ (қаз)", default="")
    question_text_en = models.TextField(blank=True, verbose_name="Question (eng)", default="")

    answer_variant_a_en = models.TextField(blank=True, null=True, verbose_name="Variant a (eng)", default="")
    answer_variant_a_kk = models.TextField(blank=True, null=True, verbose_name="A нұсқасы (қаз)", default="")
    answer_variant_a_ru = models.TextField(blank=True, null=True, verbose_name="Вариант a (рус)", default="")

    answer_variant_b_ru = models.TextField(blank=True, verbose_name="Вариант b (рус)", default="")
    answer_variant_b_kk = models.TextField(blank=True, verbose_name="B нұсқасы (қаз)", default="")
    answer_variant_b_en = models.TextField(blank=True, verbose_name="Variant b (eng)", default="")

    answer_variant_c_ru = models.TextField(blank=True, verbose_name="Вариант c (рус)", default="")
    answer_variant_c_kk = models.TextField(blank=True, verbose_name="C нұсқасы (қаз)", default="")
    answer_variant_c_en = models.TextField(blank=True, verbose_name="Variant c (eng)", default="")

    question_type = models.CharField(max_length=50, choices=QUESTION_TYPE_CHOICES, verbose_name="Тип вопроса")

    def __str__(self):
        return self.question_text_ru


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
        help_text="Чем меньше число, тем выше приоритет",
        verbose_name="Приоритет"
    )
    special_housing = models.BooleanField(
        default=False,
        verbose_name="Заселять на 1–2 этаж"
    )
    data_type = models.CharField(max_length=20, choices=DATA_TYPE_CHOICES, verbose_name="Тип данных")
    auto_fill_field = models.CharField(
        max_length=50, blank=True, null=True,
        help_text="Название поля в Application или Student, откуда брать значение при отсутствии загруженного доказательства",
        verbose_name="Поле автозаполнения"
    )
    keywords = models.ManyToManyField('Keyword', through='EvidenceKeyword', blank=True, verbose_name="Ключевые слова")

    def __str__(self):
        return self.code


class EvidenceKeyword(models.Model):
    evidence_type = models.ForeignKey(EvidenceType, on_delete=models.CASCADE,
                                      related_name='evidence_keywords', related_query_name='evidence_keyword')
    keyword = models.ForeignKey(Keyword, on_delete=models.CASCADE, related_name='evidence_keywords')

    def __str__(self):
        return f"{self.evidence_type.name} - {self.keyword.keyword}"

def upload_to_payment_screenshot(instance, filename):
    ext = os.path.splitext(filename)[1].lower()
    return f"payments/user_{instance.pk or 'new'}/{uuid.uuid4().hex}{ext}"

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
    status = models.CharField(
        max_length=20,
        choices=STATUS_CHOICES,
        default='pending',
        verbose_name="Статус"
    )
    dormitory_cost = models.PositiveIntegerField(verbose_name="Выбранная стоимость проживания")
    test_answers = models.JSONField(default=dict, verbose_name="Ответы теста")
    test_result = models.CharField(max_length=1, null=True, blank=True, verbose_name="Результат теста")

    payment_screenshot = models.FileField(
        upload_to=upload_to_payment_screenshot,
        null=True,
        blank=True,
        verbose_name="Скрин оплаты",
        storage = AzureMediaStorage()
    )

    is_full_payment = models.BooleanField(null=True, blank=True, verbose_name="Полная оплата")
    parent_phone = models.CharField(max_length=20, null=True, blank=True, verbose_name="Телефон родителей")
    ent_result = models.PositiveIntegerField(null=True, blank=True, verbose_name="Результат ЕНТ")
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время создания")
    updated_at = models.DateTimeField(auto_now=True, verbose_name="Время последнего обновления")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_payment_screenshot = self.payment_screenshot.name if self.payment_screenshot else None

    def save(self, *args, **kwargs):
        if not self.payment_screenshot:
            return super().save(*args, **kwargs)

        file_obj = getattr(self.payment_screenshot, 'file', None)

        if not file_obj:
            self.payment_screenshot = None
            return super().save(*args, **kwargs)

        print(f"File found: {self.payment_screenshot.name}, uploading to Azure.")

        super().save(*args, **kwargs)

        ext = os.path.splitext(self.payment_screenshot.name)[1].lower()
        unique_name = f"{uuid.uuid4().hex}{ext}"
        blob_path = f"payments/user_{self.pk}/{unique_name}"

        file_obj.seek(0)
        data = file_obj.read()
        service_client = BlobServiceClient(
            account_url=f"https://{settings.AZURE_ACCOUNT_NAME}.blob.core.windows.net",
            credential=settings.AZURE_ACCOUNT_KEY
        )
        container_client = service_client.get_container_client(settings.AZURE_CONTAINER)
        blob_client = container_client.get_blob_client(blob_path)
        blob_client.upload_blob(data, overwrite=True)

        self.payment_screenshot.name = blob_path
        super().save(update_fields=['payment_screenshot'])

        self._original_payment_screenshot = self.payment_screenshot.name
        print(f"File uploaded to Azure: {self.payment_screenshot.name}")



    def _handle_status_change(self, old_status, new_status):
        user = self.student
        messages = {
            'rejected': 'Статус заявки был изменен. Ваша заявка отклонена.',
            'awaiting_payment': 'Статус заявки был изменен. Ваша заявка одобрена. Внесите оплату и прикрепите квитанцию в профиле.',
            'awaiting_order': 'Статус заявки был изменен. Оплата подтверждена. Ожидайте ордер на заселение.',
            'order': 'Статус заявки был изменен. Ваш ордер готов! Подробнее в профиле.'
        }
        if new_status in messages:
            Notification.objects.create(recipient=user, message_ru=messages[new_status])

    @property
    def needs_low_floor(self) -> bool:
        return self.evidences.filter(
            approved=True,
            evidence_type__special_housing=True
        ).exists()

    def __str__(self):
        return f"Заявка от {self.student}"


class StudentInRoom(models.Model):
    application = models.OneToOneField(Application, on_delete=models.CASCADE, related_name='assignment')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='occupants')
    group = models.CharField(max_length=10, blank=True)
    assigned_at = models.DateTimeField(default=timezone.now, verbose_name="Время расселения")

    class Meta:
        unique_together = ('application', 'room')

    def __str__(self):
        return f"{self.application.student} → {self.room}"


class ApplicationEvidence(models.Model):
    application = models.ForeignKey(
        Application, on_delete=models.CASCADE,
        related_name='evidences', verbose_name="Заявка"
    )
    evidence_type = models.ForeignKey(
        EvidenceType, on_delete=models.CASCADE,
        verbose_name="Тип доказательства"
    )
    file = models.FileField(
        upload_to=evidences_upload_path,
        null=True, blank=True,
        verbose_name="Файл доказательства",
        storage=AzureMediaStorage()
    )
    numeric_value = models.DecimalField(
        max_digits=6, decimal_places=2,
        null=True, blank=True,
        verbose_name="Числовое значение"
    )
    approved = models.BooleanField(
        null=True, blank=True,
        verbose_name="Одобрено",
        help_text="True – одобрено, False – отклонено, None – не проверено"
    )
    created_at = models.DateTimeField(auto_now_add=True, verbose_name="Время создания")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._original_file_name = self.file.name

    def save(self, *args, **kwargs):
        is_new = self.pk is None
        file_obj = getattr(self.file, 'file', None)
        super().save(*args, **kwargs)

        if not file_obj or self.file.name == self._original_file_name:
            return

        ext = os.path.splitext(self.file.name)[1].lower()
        unique_name = f"{uuid.uuid4().hex}{ext}"
        blob_path = f"evidences/{unique_name}"

        file_obj.seek(0)
        data = file_obj.read()
        service = BlobServiceClient(
            account_url=f"https://{settings.AZURE_ACCOUNT_NAME}.blob.core.windows.net",
            credential=settings.AZURE_ACCOUNT_KEY
        )
        container = service.get_container_client(settings.AZURE_CONTAINER)
        container.get_blob_client(blob_path).upload_blob(data, overwrite=True)

        self.file.name = blob_path
        super().save(update_fields=['file'])

        self._original_file_name = blob_path

    def __str__(self):
        return f"{self.application.id} – {self.evidence_type.name}"


class Chat(models.Model):
    student = models.ForeignKey(User, on_delete=models.CASCADE, related_name='chats')
    status = models.CharField(max_length=30, default='waiting_for_admin')
    is_operator_connected = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Chat {self.id} - {self.student}"


class Message(models.Model):
    chat = models.ForeignKey(Chat, on_delete=models.CASCADE, related_name='messages')
    sender = models.ForeignKey(User, on_delete=models.CASCADE, related_name='sent_messages')
    receiver = models.ForeignKey(User, on_delete=models.CASCADE, related_name='received_messages', null=True,
                                 blank=True)
    content = models.TextField()
    timestamp = models.DateTimeField(auto_now_add=True)
    is_from_bot = models.BooleanField(default=False)
    operator_requested_at = models.DateTimeField(null=True, blank=True)
    objects = models.Manager()

    def __str__(self):
        return f"{self.sender} -> {self.receiver}: {self.content}"


class Notification(models.Model):
    recipient = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    message_ru = models.TextField(verbose_name="Текст уведомления (рус)")
    message_kk = models.TextField(blank=True, verbose_name="Хабарлама (қаз)")
    message_en = models.TextField(blank=True, verbose_name="Notification (eng)")
    created_at = models.DateTimeField(auto_now_add=True)
    is_read = models.BooleanField(default=False)

    def __str__(self):
        return f"Notification for {self.recipient} at {self.created_at}"


class QuestionAnswer(models.Model):
    question_ru = models.TextField(unique=True, verbose_name="Вопрос (рус)")
    question_kk = models.TextField(blank=True, verbose_name="Сұрақ (қаз)")
    question_en = models.TextField(blank=True, verbose_name="Question (eng)")
    answer_ru = models.TextField(verbose_name="Ответ (рус)")
    answer_kk = models.TextField(blank=True, verbose_name="Жауап (қаз)")
    answer_en = models.TextField(blank=True, verbose_name="Answer (eng)")

    def __str__(self):
        return f"Q: {self.question_ru[:30]}... A: {self.answer_ru[:30]}..."


class StudentInDorm(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name="Студент",
                                related_name="in_dorm_assignments", null=True)
    application = models.OneToOneField('dorm.Application', on_delete=models.CASCADE, verbose_name="Заявление",
                                       related_name="dorm_assignment", null=True)
    room = models.ForeignKey('dorm.Room', on_delete=models.CASCADE, verbose_name="Комната",
                             related_name="room_occupants", null=True, blank=True)
    group = models.CharField(max_length=10, null=True, blank=True, verbose_name="Группа")
    order = models.ImageField(upload_to='orders/', null=True, blank=True, verbose_name="Ордер")
    assigned_at = models.DateTimeField(default=timezone.now, verbose_name="Время расселения")

    class Meta:
        unique_together = ('application', 'room')
        verbose_name = "Назначение студента в комнату"
        verbose_name_plural = "Назначения студентов"

    def __str__(self):
        return f"{self.student} → {self.room or '— не назначен'}"


class KnowledgeBase(models.Model):
    question_keywords = models.TextField(verbose_name="Ключевые слова/вопрос")
    answer = models.TextField(verbose_name="Ответ")

    def __str__(self):
        return self.question_keywords[:50]


class GlobalSettings(models.Model):
    allow_application_edit = models.BooleanField(default=False, verbose_name="Студентам разрешено редактировать заявки")

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def get_solo(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    class Meta:
        verbose_name = "Глобальная настройка"
        verbose_name_plural = "Глобальные настройки"


auditlog.register(Student)
auditlog.register(Admin)
auditlog.register(Keyword)
auditlog.register(Application)
auditlog.register(StudentInDorm)
