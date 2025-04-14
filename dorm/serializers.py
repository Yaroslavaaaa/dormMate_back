from rest_framework import serializers
from .models import *
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

from .utils import calculate_application_score


class StudentSerializer(serializers.ModelSerializer):
    region = serializers.PrimaryKeyRelatedField(queryset=Region.objects.all())
    class Meta:
        model = Student
        fields = '__all__'



class RegionSerializer(serializers.ModelSerializer):
    class Meta:
        model = Region
        fields = '__all__'

class DormImageSerializer(serializers.ModelSerializer):
    class Meta:
        model = DormImage
        fields = ["id", "image"]

class DormSerializer(serializers.ModelSerializer):
    images = DormImageSerializer(many=True, read_only=True)

    class Meta:
        model = Dorm
        fields = "__all__"

class TestQuestionSerializer(serializers.ModelSerializer):
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


class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)


class MessageSerializer(serializers.ModelSerializer):
    sender_type = serializers.SerializerMethodField()

    class Meta:
        model = Message
        fields = ['id', 'content', 'timestamp', 'sender_type']

    def get_sender_type(self, obj):
        # Проверка, кто отправитель: студент или админ
        if hasattr(obj.sender, 'student'):
            return 'student'
        elif hasattr(obj.sender, 'admin') or obj.sender.is_staff or obj.sender.is_superuser:
            return 'admin'
        return 'unknown'
class ChatSerializer(serializers.ModelSerializer):
    student = serializers.SerializerMethodField()

    class Meta:
        model = Chat
        fields = ('id', 'student', 'status', 'is_active', 'created_at')

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
        fields = ['id', 'message', 'created_at', 'is_read']


class QuestionAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = '__all__'


class QuestionAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = '__all__'



class EvidenceTypeSerializer(serializers.ModelSerializer):
    # Если нужно, можно добавить alias для отображения имени
    label = serializers.CharField(source='name', read_only=True)

    class Meta:
        model = EvidenceType
        fields = ('id', 'code', 'name', 'label', 'priority', 'data_type')


class ApplicationEvidenceSerializer(serializers.ModelSerializer):
    evidence_type = serializers.SlugRelatedField(
        slug_field='code',
        read_only=True
    )

    class Meta:
        model = ApplicationEvidence
        fields = ('id', 'evidence_type', 'file', 'numeric_value', 'approved', 'created_at')




class ApplicationSerializer(serializers.ModelSerializer):
    student = StudentSerializer(read_only=True)
    evidences = ApplicationEvidenceSerializer(many=True, required=False)
    score = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = Application
        fields = (
            'id',
            'student',
            'approval',
            'status',
            'dormitory_cost',
            'test_answers',
            'test_result',
            'payment_screenshot',
            'ent_result',
            'gpa',
            'evidences',
            'score',
            'created_at',
            'updated_at',
        )

    def get_score(self, obj):
        try:
            return calculate_application_score(obj)
        except Exception as e:
            # Логируем ошибку, чтобы понять, что именно происходит
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



class StudentInDormSerializer(serializers.ModelSerializer):
    # Вложенное представление для студента, заявление и общежития.
    student = StudentSerializer(source='student_id', read_only=True)
    application = ApplicationSerializer(source='application_id', read_only=True)
    dorm = DormSerializer(source='dorm_id', read_only=True)

    class Meta:
        model = StudentInDorm
        fields = [
            'id',
            'student',      # вложенные данные по студенту
            'dorm',         # вложенные данные по общежитию
            'group',        # номер группы/комнаты
            'application',  # вложенные данные по заявке
            'order',
            'room'
        ]