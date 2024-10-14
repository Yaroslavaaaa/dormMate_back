from rest_framework import serializers
from .models import *

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



class QuestionAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = ['id', 'question', 'answer']




class QuestionOnlySerializer(serializers.ModelSerializer):
    class Meta:
        model = QuestionAnswer
        fields = ['id', 'question']