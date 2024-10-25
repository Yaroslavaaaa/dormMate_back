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
        fields = ['id', 'question_text', 'question_type', 'answers']

class ApplicationSerializer(serializers.ModelSerializer):
    student = StudentSerializer(read_only=True)

    class Meta:
        model = Application
        fields = ['student', 'dormitory_choice']
        # fields = '__all__'

class ExcelUploadSerializer(serializers.Serializer):
    file = serializers.FileField()

class CustomTokenObtainSerializer(serializers.Serializer):
    s = serializers.CharField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        s = data.get('s')
        password = data.get('password')

        if s and password:
            user = authenticate(request=self.context.get('request'), s=s, password=password)
            print(s, password)
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
            raise serializers.ValidationError('Must include "s" and "password"')

class QuestionAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = ['id', 'question', 'answer']

class QuestionOnlySerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = ['id', 'question']
