from rest_framework import viewsets, status, generics, filters
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

class TestQuestionViewSet(generics.ListAPIView):
    queryset = TestQuestion.objects.all()
    serializer_class = TestQuestionSerializer

class ApplicationViewSet(generics.ListAPIView):
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer




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
        dormitory_choice_id = request.data.get('dormitory_choice')

        if not student_id:
            return Response({"error": "Поле 'student' обязательно"}, status=status.HTTP_400_BAD_REQUEST)

        if not dormitory_choice_id:
            return Response({"error": "Поле 'dormitory_choice' обязательно"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            return Response({"error": "Студент с таким ID не найден"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            dormitory_choice = Dorm.objects.get(pk=dormitory_choice_id)
        except Dorm.DoesNotExist:
            return Response({"error": "Общежитие с таким ID не найдено"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ApplicationSerializer(data=request.data)
        if serializer.is_valid():
            application = serializer.save(student=student, dormitory_choice=dormitory_choice)
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







class ApplicationStatusView(APIView):
    def get(self, request, student_id):
        applications = Application.objects.filter(student__id=student_id)

        if not applications.exists():
            return Response({"error": "Заявки не найдены для данного студента"}, status=status.HTTP_404_NOT_FOUND)

        application = applications.first()

        if not application.approval:
            return Response({"status": "Заявка на рассмотрении"}, status=status.HTTP_200_OK)

        if application.approval and not application.payment_screenshot:
            return Response({
                "status": "Заявка одобрена, внесите оплату и прикрепите скрин.",
                "payment_url": "http://127.0.0.1:8000/api/v1/upload_payment_screenshot/<int:student_id>/"
            }, status=status.HTTP_200_OK)

        if application.approval and application.payment_screenshot:
            return Response({"status": "Заявка принята, ожидайте ордер."}, status=status.HTTP_200_OK)

        return Response({"error": "Неизвестный статус заявки"}, status=status.HTTP_400_BAD_REQUEST)


class UploadPaymentScreenshotView(APIView):
    def post(self, request, student_id):
        try:
            application = Application.objects.get(student_id=student_id, approval=True)
        except Application.DoesNotExist:
            return Response({"error": "Заявка не найдена или не одобрена"}, status=status.HTTP_404_NOT_FOUND)

        payment_screenshot = request.FILES.get('payment_screenshot')
        if not payment_screenshot:
            return Response({"error": "Необходимо прикрепить скрин оплаты"}, status=status.HTTP_400_BAD_REQUEST)

        application.payment_screenshot = payment_screenshot
        application.save()

        return Response({"message": "Скрин оплаты успешно прикреплен, заявка принята. Ожидайте ордер."}, status=status.HTTP_200_OK)



class QuestionViewSet(generics.ListCreateAPIView):
    queryset = QuestionAnswer.objects.all()
    serializer_class = QuestionAnswerSerializer

    def perform_create(self, serializer):
        serializer.save()



class AnswerDetailView(generics.RetrieveAPIView):
    queryset = QuestionAnswer.objects.all()
    serializer_class = QuestionAnswerSerializer

    def retrieve(self, request, *args, **kwargs):
        instance = self.get_object()
        return Response({"question": instance.question, "answer": instance.answer})



class QuestionAnswerViewSet(generics.ListAPIView):
    queryset = QuestionAnswer.objects.all()
    filter_backends = [filters.SearchFilter]
    search_fields = ['question']

    def get_serializer_class(self):
        if 'search' in self.request.query_params:
            return QuestionAnswerSerializer
        return QuestionOnlySerializer

