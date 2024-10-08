from rest_framework import viewsets, status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
import pandas as pd
from thefuzz import process
from .models import *
from .serializers import *
from collections import Counter
from rest_framework_simplejwt.tokens import RefreshToken
from django.contrib.auth import authenticate


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


class ExcelUploadView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = ExcelUploadSerializer(data=request.data)
        if serializer.is_valid():
            if 'file' not in request.FILES:
                return Response({"error": "Файл не загружен"}, status=status.HTTP_400_BAD_REQUEST)

            try:
                excel_file = request.FILES['file']
                df = pd.read_excel(excel_file)
            except Exception as e:
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

            all_regions = Region.objects.values_list('region_name', flat=True)

            for index, row in df.iterrows():
                region_name = row['region_name']

                extract_result = process.extractOne(region_name, all_regions)

                if extract_result is None:
                    return Response({"error": f"Не удалось найти похожие регионы для '{region_name}'"},
                                    status=status.HTTP_400_BAD_REQUEST)

                closest_region_name, score = extract_result

                if score < 80:
                    return Response({"error": f"Не удалось найти подходящий регион для '{region_name}'"},
                                    status=status.HTTP_400_BAD_REQUEST)

                region = Region.objects.get(region_name=closest_region_name)

                student, created = Student.objects.update_or_create(
                    student_s=row['student_s'],
                    defaults={
                        'first_name': row['first_name'],
                        'last_name': row['last_name'],
                        'middle_name': row['middle_name'],
                        'region': region,
                        'course': row['course'],
                        'email': row['email']
                    }
                )


            return Response({"status": "success", "data": "Данные успешно загружены и обновлены"},
                            status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)






class CreateApplicationView(APIView):
    def post(self, request):
        student_id = request.data.get('student')
        if not student_id:
            return Response({"error": "Поле 'student' обязательно"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            return Response({"error": "Студент с таким ID не найден"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ApplicationSerializer(data=request.data)
        if serializer.is_valid():
            application = serializer.save(student=student)
            return Response({"message": "Заявка создана", "application_id": application.id},
                            status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)



class TestView(APIView):
    def post(self, request, pk):
        try:
            application = Application.objects.get(pk=pk)
        except Application.DoesNotExist:
            return Response({"error": "Заявка не найдена"}, status=status.HTTP_404_NOT_FOUND)

        test_answers = request.data.get('test_answers')
        if not test_answers:
            return Response({"error": "Необходимо предоставить ответы на тест"}, status=status.HTTP_400_BAD_REQUEST)

        letter_count = Counter(test_answers)
        most_common_letter = letter_count.most_common(1)[0][0]

        application.test_answers = test_answers
        application.test_result = most_common_letter
        application.save()

        return Response({"message": "Ваша заявка принята", "result_letter": most_common_letter}, status=status.HTTP_200_OK)



class CustomTokenObtainView(APIView):
    def post(self, request):
        username = request.data.get('username')
        password = request.data.get('password')

        user = authenticate(request, username=username, password=password)
        if user is not None:
            refresh = RefreshToken.for_user(user)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'type': 'user',
            })

        email = request.data.get('email')
        student = authenticate(request, email=email, password=password)
        if student is not None:
            refresh = RefreshToken.for_user(student)
            return Response({
                'refresh': str(refresh),
                'access': str(refresh.access_token),
                'type': 'student',
            })

        return Response({'detail': 'Invalid credentials'}, status=status.HTTP_401_UNAUTHORIZED)