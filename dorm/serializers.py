from rest_framework import serializers
from .models import *
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

class StudentSerializer(serializers.ModelSerializer):
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

# class ApplicationSerializer(serializers.ModelSerializer):
#     student = StudentSerializer(read_only=True)
#
#     class Meta:
#         model = Application
#         fields = ['student', 'dormitory_choice']
#         # fields = '__all__'


class ApplicationSerializer(serializers.ModelSerializer):
    student = StudentSerializer(read_only=True)
    # dormitory_name = serializers.CharField(source='dormitory.name', read_only=True)

    class Meta:
        model = Application
        fields = '__all__'  # Все поля модели Application
        # extra_fields = ['dormitory_name']  # Добавляемое поле

    # def to_representation(self, instance):
    #     representation = super().to_representation(instance)
    #     representation['dormitory_name'] = instance.dormitory_choice.name if instance.dormitory_choice else None
    #     return representation


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
