from rest_framework import serializers
from .models import *
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate

class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = '__all__'

class DormSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dorm
        fields = '__all__'

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
    dormitory_name = serializers.CharField(source='dormitory.name', read_only=True)

    class Meta:
        model = Application
        fields = '__all__'  # Все поля модели Application
        extra_fields = ['dormitory_name']  # Добавляемое поле

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation['dormitory_name'] = instance.dormitory_choice.name if instance.dormitory_choice else None
        return representation


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

class QuestionAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = ['id', 'question', 'answer']

class QuestionOnlySerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = ['id', 'question']

class ChangePasswordSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)
