from rest_framework import viewsets, status, generics
from rest_framework.response import Response
from .models import Student, Dorm, TestQuestion, TestAnswer, Application, TestResult
from .serializers import StudentSerializer, DormSerializer, TestQuestionSerializer, ApplicationSerializer, TestResultSerializer

class StudentViewSet(generics.ListAPIView):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer

class DormViewSet(generics.ListAPIView):
    queryset = Dorm.objects.all()
    serializer_class = DormSerializer

class TestQuestionViewSet(viewsets.ModelViewSet):
    queryset = TestQuestion.objects.all()
    serializer_class = TestQuestionSerializer

class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer

class TestResultViewSet(viewsets.ModelViewSet):
    queryset = TestResult.objects.all()
    serializer_class = TestResultSerializer

    def create(self, request, *args, **kwargs):
        # Получаем результаты теста и сохраняем их
        test_data = request.data.get('test_results', [])
        application = Application.objects.get(id=request.data.get('application_id'))
        total_score = 0

        for result in test_data:
            question = TestQuestion.objects.get(id=result['question_id'])
            answer = TestAnswer.objects.get(id=result['answer_id'])
            TestResult.objects.create(application=application, question=question, selected_answer=answer)
            total_score += answer.score

        application.test_result = total_score / len(test_data)  # Рассчитываем средний результат
        application.save()

        return Response({'status': 'Test results saved', 'total_score': total_score}, status=status.HTTP_201_CREATED)
