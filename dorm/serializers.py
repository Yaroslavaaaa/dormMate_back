from rest_framework import serializers
from .models import *
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate
import bleach
from .utils import calculate_application_score
from auditlog.models import LogEntry
from rest_framework import serializers


def sanitize_string(value):
    return bleach.clean(value, tags=[], attributes={}, strip=True) if isinstance(value, str) else value


def sanitize_data(data, serializer):
    for field_name, field in serializer.fields.items():
        if field_name not in data:
            continue

        value = data[field_name]

        if isinstance(field, serializers.CharField) and isinstance(value, str):
            data[field_name] = sanitize_string(value)

        elif isinstance(field, serializers.ListSerializer):
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        sanitize_data(item, field.child)

        elif isinstance(field, serializers.ModelSerializer) and isinstance(value, dict):
            sanitize_data(value, field)

    return data


class SanitizedModelSerializer(serializers.ModelSerializer):
    def validate(self, data):
        return sanitize_data(data, self)


class StudentSerializer(SanitizedModelSerializer):
    region = serializers.PrimaryKeyRelatedField(queryset=Region.objects.all())

    class Meta:
        model = Student
        fields = '__all__'


class GlobalSettingsSerializer(SanitizedModelSerializer):
    class Meta:
        model = GlobalSettings
        fields = ['allow_application_edit']


class AdminSerializer(SanitizedModelSerializer):
    password = serializers.CharField(write_only=True, required=False)

    class Meta:
        model = Admin
        fields = [
            'id', 's', 'first_name', 'last_name', 'middle_name',
            'email', 'birth_date', 'phone_number', 'avatar', 'gender',
            'is_active', 'is_staff', 'role', 'password',
        ]
        read_only_fields = ['id', 'is_staff']

    def validate_s(self, value):
        if not re.fullmatch(r'F\d{8}', value):
            raise serializers.ValidationError(
                'Admin "s" must start with "F" followed by exactly eight digits.'
            )
        return value.upper()

    def create(self, validated_data):
        password = validated_data.pop('password')
        admin = Admin(**validated_data)
        admin.set_password(password)
        admin.is_staff = True
        admin.save()
        return admin

    def update(self, instance, validated_data):
        password = validated_data.pop('password', None)
        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        if password:
            instance.set_password(password)
        instance.save()
        return instance


class RegionSerializer(SanitizedModelSerializer):
    class Meta:
        model = Region
        fields = '__all__'


class DormImageSerializer(SanitizedModelSerializer):
    class Meta:
        model = DormImage
        fields = ["id", "image"]


class DormSerializer(SanitizedModelSerializer):
    images = DormImageSerializer(many=True, read_only=True)
    floors_count = serializers.IntegerField(read_only=True)

    class Meta:
        model = Dorm
        fields = "__all__"


class TestQuestionSerializer(SanitizedModelSerializer):
    class Meta:
        model = TestQuestion
        fields = "__all__"


class ExcelUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class CustomTokenObtainSerializer(serializers.Serializer):
    s = serializers.CharField(required=False)
    phone_number = serializers.CharField(required=False)
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        s = data.get('s')
        phone_number = data.get('phone_number')
        password = data.get('password')

        if (s or phone_number) and password:
            user = authenticate(
                request=self.context.get('request'),
                s=s,
                phone_number=phone_number,
                password=password
            )
            if user:
                if not user.is_active:
                    raise serializers.ValidationError('User is inactive')

                refresh = RefreshToken.for_user(user)
                return {
                    'refresh': str(refresh),
                    'access': str(refresh.access_token),
                }
            else:
                raise serializers.ValidationError('Invalid credentials')
        else:
            raise serializers.ValidationError('Must include "s" or "phone_number" and "password"')


class ChangePasswordSerializer(SanitizedModelSerializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)


class MessageSerializer(SanitizedModelSerializer):
    sender_type = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'content', 'timestamp', 'sender_type']

    def get_sender_type(self, obj):
        if hasattr(obj.sender, 'student'):
            return 'student'
        elif hasattr(obj.sender, 'admin') or obj.sender.is_staff or obj.sender.is_superuser:
            return 'admin'
        return 'unknown'


class ChatSerializer(SanitizedModelSerializer):
    student = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = ('id', 'student', 'status', 'is_active', 'created_at', 'is_operator_connected')

    def get_student(self, obj):
        return {
            'id': obj.student.id,
            's': obj.student.s,
            'first_name': obj.student.first_name,
            'last_name': obj.student.last_name,
        }


class NotificationSerializer(serializers.ModelSerializer):
    class Meta:
        model = Notification
        fields = ['id', 'recipient', 'message_ru', 'message_kk', 'message_en', 'created_at', 'is_read']

        def get_message(self, obj):
            # Получаем язык из запроса, например Accept-Language, или по другому методу
            request = self.context.get('request')
            lang = 'ru'
            if request:
                lang = request.LANGUAGE_CODE
            if lang == 'kk':
                return obj.message_kk or obj.message_ru or obj.message_en or ''
            elif lang == 'en':
                return obj.message_en or obj.message_ru or obj.message_kk or ''
            return obj.message_ru or obj.message_kk or obj.message_en or ''



class QuestionAnswerSerializer(SanitizedModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = '__all__'


class QuestionAnswerSerializer(SanitizedModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = '__all__'


class KnowledgeBaseSerializer(SanitizedModelSerializer):
    class Meta:
        model = KnowledgeBase
        fields = ['id', 'question_keywords', 'answer']


class EvidenceTypeSerializer(SanitizedModelSerializer):
    keywords = serializers.PrimaryKeyRelatedField(
        many=True,
        queryset=Keyword.objects.all()
    )

    class Meta:
        model = EvidenceType
        fields = [
            'id',
            'name',
            'code',
            'priority',
            'data_type',
            'auto_fill_field',
            'keywords',
        ]
        read_only_fields = ['id']

    def create(self, validated_data):
        kw_list = validated_data.pop('keywords', [])
        print(">> EvidenceType.create(), keywords payload:", kw_list)

        evidence = EvidenceType.objects.create(**validated_data)

        for kw in kw_list:
            EvidenceKeyword.objects.create(
                evidence_type=evidence,
                keyword=kw
            )
        return evidence

    def update(self, instance, validated_data):
        kw_list = validated_data.pop('keywords', None)
        print(">> EvidenceType.update(), keywords payload:", kw_list)

        for attr, val in validated_data.items():
            setattr(instance, attr, val)
        instance.save()

        if kw_list is not None:
            EvidenceKeyword.objects.filter(evidence_type=instance).delete()
            for kw in kw_list:
                EvidenceKeyword.objects.create(
                    evidence_type=instance,
                    keyword=kw
                )
        return instance


class ApplicationEvidenceSerializer(SanitizedModelSerializer):
    evidence_type_code = serializers.CharField(source='evidence_type.code')

    class Meta:
        model = ApplicationEvidence
        fields = ['id', 'evidence_type_code', 'file', 'approved']


class ApplicationSerializer(SanitizedModelSerializer):
    student = StudentSerializer(read_only=True)
    evidences = ApplicationEvidenceSerializer(many=True, required=False)
    score = serializers.SerializerMethodField(read_only=True)
    gpa = serializers.SerializerMethodField()
    dormitory_cost = serializers.IntegerField(required=True)
    parent_phone = serializers.CharField(required=False, allow_blank=True, allow_null=True)
    ent_result = serializers.IntegerField(required=False, allow_null=True)
    test_answers = serializers.JSONField(required=False, allow_null=True)
    test_result = serializers.CharField(required=False, allow_null=True)

    # и так далее...

    class Meta:
        model = Application
        fields = '__all__'
        read_only_fields = [
            'id', 'student', 'approval', 'status', 'payment_screenshot',
            'is_full_payment', 'created_at', 'updated_at'
        ]

    def get_gpa(self, obj):
        if obj.student:
            return obj.student.gpa
        return None

    def get_score(self, obj):
        try:
            return calculate_application_score(obj)
        except Exception as e:
            import logging
            logger = logging.getLogger(__name__)
            logger.error("Error calculating score for application %s: %s", obj.id, e)
            return None

    def create(self, validated_data):
        evidences_data = validated_data.pop('evidences', [])
        application = Application.objects.create(**validated_data)
        for evidence_data in evidences_data:
            ApplicationEvidence.objects.create(application=application, **evidence_data)
        return application

    def update(self, instance, validated_data):
        evidences_data = validated_data.pop('evidences', None)
        for attr, value in validated_data.items():
            setattr(instance, attr, value)
        instance.save()
        if evidences_data is not None:
            instance.evidences.all().delete()
            for evidence_data in evidences_data:
                ApplicationEvidence.objects.create(application=instance, **evidence_data)
        return instance


class RoomSerializer(serializers.ModelSerializer):
    # Позволяем передавать внешнему ключу “dorm” именно ID
    dorm = serializers.PrimaryKeyRelatedField(
        queryset=Dorm.objects.all()
    )

    class Meta:
        model = Room
        # перечисляем только реальные поля модели (и внешн. ключ dorm)
        fields = (
            'id',
            'dorm',
            'number',
            'capacity',
            'floor',
        )
        # floor пусть будет read-only, его вычисляет модель
        read_only_fields = ('id', 'floor')

    def get_free_spots(self, room: Room):
        occupied_count = room.room_occupants.count()
        free = room.capacity - occupied_count
        return free if free >= 0 else 0


#upd
class StudentInDormSerializer(serializers.ModelSerializer):
    student = StudentSerializer(read_only=True)
    application = ApplicationSerializer(read_only=True)

    # Вложенный RoomSerializer для GET
    room = RoomSerializer(read_only=True)

    # Дополнительное поле для записи (PATCH) — присвоение комнаты по ID
    room_id = serializers.PrimaryKeyRelatedField(
        queryset=Room.objects.all(),
        source="room",
        write_only=True,
        required=False,
        allow_null=True
    )

    # Вложенный DormSerializer — название общежития приходит как часть room.dorm,
    # но оставим и явное поле, если нужно сразу достать dorm без room.
    dorm = DormSerializer(read_only=True, source="room.dorm")

    class Meta:
        model = StudentInDorm
        fields = [
            'id',
            'student',
            'application',
            'dorm',        # название общежития (берётся из room.dorm)
            'room',        # RoomSerializer (nested)
            'room_id',     # нужен для записи PATCH { "room_id": 12 }
            'group',
            'order',
            'assigned_at',
        ]


class KeywordSerializer(SanitizedModelSerializer):
    class Meta:
        model = Keyword
        fields = ['id', 'keyword']
        read_only_fields = ['id']


class AuditLogSerializer(serializers.ModelSerializer):
    actor_name = serializers.SerializerMethodField()
    model_name = serializers.SerializerMethodField()
    model_verbose_name = serializers.SerializerMethodField()
    action_type = serializers.SerializerMethodField()

    class Meta:
        model = LogEntry
        fields = [
            'id',
            'timestamp',
            'actor_name',
            'action',
            'action_type',
            'content_type',
            'model_name',
            'model_verbose_name',
            'object_id',
            'object_repr',
            'changes',
        ]

    def get_actor_name(self, obj):
        if obj.actor:
            return f"{obj.actor.first_name} {obj.actor.last_name}".strip() or "actor"
        return "Система"

    def get_model_name(self, obj):
        """Возвращает техническое название модели"""
        if obj.content_type:
            return obj.content_type.model
        return None

    def get_model_verbose_name(self, obj):
        """Возвращает человекочитаемое название модели"""
        if obj.content_type:
            model_class = obj.content_type.model_class()
            if model_class:
                return model_class._meta.verbose_name
        return None

    def get_action_type(self, obj):
        """Возвращает тип действия в человекочитаемом формате"""
        action_mapping = {
            0: 'Создание',
            1: 'Изменение',
            2: 'Удаление',
        }
        return action_mapping.get(obj.action, f'Неизвестное действие (код: {obj.action})')


