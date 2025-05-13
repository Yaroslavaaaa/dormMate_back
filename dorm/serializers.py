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



class GlobalSettingsSerializer(serializers.ModelSerializer):
    class Meta:
        model = GlobalSettings
        fields = ['allow_application_edit']



class AdminSerializer(serializers.ModelSerializer):
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
        fields = ['id', 'message', 'created_at', 'is_read']


class QuestionAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = '__all__'


class QuestionAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = '__all__'

class KnowledgeBaseSerializer(serializers.ModelSerializer):
    class Meta:
        model = KnowledgeBase
        fields = ['id', 'question_keywords', 'answer']


class EvidenceTypeSerializer(serializers.ModelSerializer):
    # включаем m2m поле
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


class ApplicationEvidenceSerializer(serializers.ModelSerializer):
    evidence_type_code = serializers.CharField(source='evidence_type.code')

    class Meta:
        model = ApplicationEvidence
        fields = ['id', 'evidence_type_code', 'file', 'approved']




class ApplicationSerializer(serializers.ModelSerializer):
    student = StudentSerializer(read_only=True)
    evidences = ApplicationEvidenceSerializer(many=True, required=False)
    score = serializers.SerializerMethodField(read_only=True)
    gpa = serializers.SerializerMethodField()

    class Meta:
        model = Application
        fields = '__all__'
        read_only_fields = [
            'id',
            'student',
            'approval',
            'status',
            'payment_screenshot',
            'is_full_payment',
            'created_at',
            'updated_at',
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



class StudentInDormSerializer(serializers.ModelSerializer):
    student = StudentSerializer(source='student_id', read_only=True)
    application = ApplicationSerializer(source='application_id', read_only=True)
    dorm = DormSerializer(source='dorm_id', read_only=True)

    class Meta:
        model = StudentInDorm
        fields = [
            'id',
            'student',
            'dorm',
            'group',
            'application',
            'order',
            'room'
        ]


class KeywordSerializer(serializers.ModelSerializer):
    class Meta:
        model = Keyword
        fields = ['id', 'keyword']
        read_only_fields = ['id']