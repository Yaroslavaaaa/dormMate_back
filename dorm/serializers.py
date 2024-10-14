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
    answers = serializers.SerializerMethodField()

    class Meta:
        model = TestQuestion
        fields = ['id', 'question_text', 'question_type', 'answers']

    def get_answers(self, obj):
        answers = obj.answers.all()
        return TestAnswerSerializer(answers, many=True).data

class TestAnswerSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestAnswer
        fields = ['id', 'answer_text', 'score']

class ApplicationSerializer(serializers.ModelSerializer):
    student = StudentSerializer(read_only=True)

    class Meta:
        model = Application
        fields = ['student', 'dormitory_choice']
        # fields = '__all__'

class TestResultSerializer(serializers.ModelSerializer):
    class Meta:
        model = TestResult
        fields = '__all__'


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