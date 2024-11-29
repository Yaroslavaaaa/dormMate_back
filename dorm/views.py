from rest_framework import viewsets, status, generics, filters
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response
import pandas as pd
from thefuzz import process
from datetime import datetime
from .models import *
from .serializers import *
from collections import Counter
from django.db import transaction
from collections import defaultdict
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import NotFound
from django.contrib.auth import authenticate
from django.http import HttpResponse

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




class StudentDetailView(RetrieveUpdateAPIView):
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        try:
            return self.request.user.student
        except Student.DoesNotExist:
            raise NotFound("Студент с таким токеном не найден.")


class IsAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        return is_authenticated and (hasattr(request.user, 'admin') or request.user.is_superuser)

class ExcelUploadView(APIView):
    permission_classes = [IsAdmin]
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

            GENDER_MAP = {
                'мужской': 'M',
                'женский': 'F',
            }

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

                birth_date_str = row['birth_date']
                try:
                    birth_date = datetime.strptime(birth_date_str, '%Y-%m-%d')
                except ValueError:
                    return Response({"error": f"Неверный формат даты рождения для студента {row['student_s']}"},
                                    status=status.HTTP_400_BAD_REQUEST)

                gender_raw = row.get('gender', '').strip().lower()
                gender = GENDER_MAP.get(gender_raw)

                if not gender:
                    return Response(
                        {"error": f"Некорректное значение пола '{gender_raw}' для студента {row['student_s']}"},
                        status=status.HTTP_400_BAD_REQUEST
                    )


                password = birth_date.strftime('%d%m%Y')

                student, created = Student.objects.update_or_create(
                    s=row['student_s'],
                    defaults={
                        'first_name': row['first_name'],
                        'last_name': row['last_name'],
                        'middle_name': row['middle_name'],
                        'region': region,
                        'course': row['course'],
                        'email': row['email'],
                        'birth_date': birth_date,
                        'gender': gender,
                        'is_active': True,
                    }
                )

                if created:
                    student.set_password(password)
                    student.save()

            return Response({"status": "success", "data": "Данные успешно загружены и обновлены"},
                            status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class IsStudent(IsAuthenticated):
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        return is_authenticated and hasattr(request.user, 'student')

class CreateApplicationView(APIView):
    permission_classes = [IsStudent]
    def post(self, request):
        student_id = request.user.student.id
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

        file_fields = [
            'priority',
            'orphan_certificate',
            'disability_1_2_certificate',
            'disability_3_certificate',
            'parents_disability_certificate',
            'loss_of_breadwinner_certificate',
            'social_aid_certificate',
            'mangilik_el_certificate',
            'olympiad_winner_certificate',
        ]

        for field in file_fields:
            file = request.FILES.get(field)
            if file:
                if file.content_type != 'application/pdf':
                    return Response(
                        {"error": f"Поле '{field}' принимает только файлы формата PDF."},
                        status=status.HTTP_400_BAD_REQUEST
                    )

        serializer = ApplicationSerializer(data=request.data)
        if serializer.is_valid():
            application = serializer.save(student=student, dormitory_choice=dormitory_choice)
            for field in file_fields:
                file = request.FILES.get(field)
                if file:
                    setattr(application, field, file)
            application.save()

            return Response({"message": "Заявка создана", "application_id": application.id},
                            status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class TestView(APIView):
    permission_classes = [IsStudent]
    def post(self, request):
        student_id = request.user.student.id
        try:
            application = Application.objects.get(student__id=student_id)
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
    def post(self, request, *args, **kwargs):
        serializer = CustomTokenObtainSerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)




class ApplicationStatusView(APIView):
    permission_classes = [IsStudent]

    def get(self, request):
        student_id = request.user.student.id
        application = Application.objects.filter(student__id=student_id).first()

        if not application:
            return Response({"error": "Заявки не найдены для данного студента"}, status=status.HTTP_404_NOT_FOUND)

        if application.status == 'pending':
            return Response({"status": "Заявка на рассмотрении"}, status=status.HTTP_200_OK)

        if application.status == 'approved':
            return Response({"status": "Ваша заявка одобрена, внесите оплату и прикрепите сюда чек.",
                "payment_url": "http://127.0.0.1:8000/api/v1/upload_payment_screenshot/"}, status=status.HTTP_200_OK)

        if application.status == 'rejected':
            return Response({"status": "Ваша заявка была отклонена."}, status=status.HTTP_200_OK)

        if application.status == 'awaiting_payment':
            return Response({
                "status": "Ваша заявка одобрена, внесите оплату и прикрепите сюда чек.",
                "payment_url": "http://127.0.0.1:8000/api/v1/upload_payment_screenshot/"
            }, status=status.HTTP_200_OK)

        if application.status == 'awaiting_order':
            return Response({"status": "Ваша заявка принята, ожидайте ордер на заселение."}, status=status.HTTP_200_OK)

        return Response({"error": "Неизвестный статус заявки"}, status=status.HTTP_400_BAD_REQUEST)


class UploadPaymentScreenshotView(APIView):
    permission_classes = [IsStudent]

    def post(self, request):
        student_id = request.user.student.id

        try:
            application = Application.objects.get(student_id=student_id, approval=True)
        except Application.DoesNotExist:
            return Response({"error": "Заявка не найдена или не одобрена"}, status=status.HTTP_404_NOT_FOUND)

        payment_screenshot = request.FILES.get('payment_screenshot')
        if not payment_screenshot:
            return Response({"error": "Необходимо прикрепить скрин оплаты"}, status=status.HTTP_400_BAD_REQUEST)

        if payment_screenshot.content_type != "application/pdf":
            return Response({"error": "Можно загружать только файлы формата PDF"}, status=status.HTTP_400_BAD_REQUEST)

        application.payment_screenshot = payment_screenshot
        application.status = "awaiting_order"
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





class DistributeStudentsAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        total_places = Dorm.objects.aggregate(total_places=models.Sum('total_places'))['total_places']

        if not total_places or total_places <= 0:
            return Response({"detail": "Нет доступных мест в общежитиях."}, status=status.HTTP_400_BAD_REQUEST)

        pending_applications = Application.objects.filter(approval=False, status="pending").select_related('student')

        print(f"Всего заявок: {len(pending_applications)}")

        sorted_applications = sorted(
            pending_applications,
            key=lambda app: (
                bool(app.orphan_certificate) or bool(app.disability_1_2_certificate),
                bool(app.disability_3_certificate) or
                bool(app.parents_disability_certificate) or
                bool(app.loss_of_breadwinner_certificate) or
                bool(app.social_aid_certificate),
                bool(app.mangilik_el_certificate),
                1 if app.student.course == "1" and app.olympiad_winner_certificate else 0,
                1 if app.student.course == "1" else 0,
                -(app.ent_result or 0) if app.student.course == "1" else 0,
                0 if app.student.course == "1" else -(app.gpa or 0),
                app.id
            ),
            reverse=True,
        )

        selected_applications = sorted_applications[:total_places]
        rejected_applications = sorted_applications[total_places:]

        print(f"Одобренных: {len(selected_applications)}")
        print(f"Отклоненных: {len(rejected_applications)}")

        approved_students = []

        with transaction.atomic():
            for application in selected_applications:
                application.approval = True
                application.status = "awaiting_payment"
                application.save()

                print(f"Одобрен: {application.student.first_name}, Курс: {application.student.course}")

                approved_students.append({
                    "student_s": getattr(application.student, "s", "Нет S"),
                    "first_name": getattr(application.student, 'first_name', 'Нет имени'),
                    "last_name": getattr(application.student, 'last_name', 'Нет имени'),
                    "course": getattr(application.student, 'course', 'Не указан'),
                    "ent_result": application.ent_result,
                    "gpa": application.gpa,
                })

            for application in rejected_applications:
                application.status = "rejected"
                application.save()

        return Response(
            {
                "detail": f"{len(selected_applications)} студентов были одобрены для заселения.",
                "approved_students": approved_students
            },
            status=status.HTTP_200_OK
        )




class DistributeStudentsAPIView2(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        dorms = Dorm.objects.all()

        approved_applications = Application.objects.filter(
            approval=True,
            payment_screenshot__isnull=False
        ).exclude(payment_screenshot="")

        grouped_applications = defaultdict(list)
        for app in approved_applications:
            grouped_applications[app.test_result].append(app)

        print("Общее количество одобренных заявок с оплатой:", approved_applications.count())
        for test_result, apps in grouped_applications.items():
            print(f"Количество студентов с результатом теста '{test_result}': {len(apps)}")

        allocated_students = []

        with transaction.atomic():
            for dorm in dorms:
                room_counts = {
                    2: dorm.rooms_for_two,
                    3: dorm.rooms_for_three,
                    4: dorm.rooms_for_four
                }

                room_number = 101
                room_suffix = 'А'

                for room_size, available_rooms in room_counts.items():
                    for _ in range(available_rooms):
                        students_for_room = []
                        for test_result, test_group in grouped_applications.items():
                            if len(test_group) >= room_size:
                                students_for_room = [
                                    student for student in test_group[:room_size]
                                    if not StudentInDorm.objects.filter(student_id=student.student).exists()
                                ]
                                grouped_applications[test_result] = [
                                    student for student in test_group if student not in students_for_room
                                ]
                                break

                        if len(students_for_room) != room_size:
                            remaining_students = [
                                student for group in grouped_applications.values() for student in group
                                if not StudentInDorm.objects.filter(student_id=student.student).exists()
                            ]
                            if remaining_students:
                                students_for_room = remaining_students[:room_size]
                                for student in students_for_room:
                                    grouped_applications[student.test_result].remove(student)

                        if len(students_for_room) == 0:
                            continue

                        room_label = f"{room_number}-{room_suffix}"
                        print(f"Комната размером {room_size} в общежитии {dorm.id} получает студентов:",
                              [student_application.student.id for student_application in students_for_room])

                        for student_application in students_for_room:
                            student_in_dorm = StudentInDorm.objects.create(
                                student_id=student_application.student,
                                dorm_id=dorm,
                                room=room_label,
                                application_id=student_application
                            )
                            allocated_students.append({
                                "student_s": getattr(student_in_dorm.student_id, "s", "Нет S"),
                                "first_name": getattr(student_in_dorm.student_id, "first_name", "Нет имени"),
                                "last_name": getattr(student_in_dorm.student_id, "last_name", "Нет фамилии"),
                                "dorm_id": getattr(student_in_dorm.dorm_id, "name", "Нет фамилии"),
                                "room": student_in_dorm.room
                            })

                        if room_suffix == 'А':
                            room_suffix = 'Б'
                        else:
                            room_suffix = 'А'
                            room_number += 1

        allocated_count = len(allocated_students)
        print("Общее количество студентов, добавленных в StudentInDorm:", allocated_count)

        return Response(
            {
                "detail": "Студенты успешно распределены по комнатам.",
                "allocated_students": allocated_students
            },
            status=status.HTTP_200_OK
        )






class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        try:
            refresh_token = request.data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response({"detail": "Logout successful"}, status=200)
        except Exception:
            return Response({"detail": "Invalid token"}, status=400)


class UserTypeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        if hasattr(user, 'student'):
            user_type = 'student'
        elif hasattr(user, 'admin') or user.is_superuser:
            user_type = 'admin'
        else:
            user_type = 'unknown'

        return Response({"user_type": user_type})


class ChangePasswordView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        user = request.user

        if not hasattr(user, 'student'):
            return Response({"error": "Only students can change passwords."}, status=status.HTTP_403_FORBIDDEN)

        old_password = request.data.get('old_password')
        new_password = request.data.get('new_password')
        confirm_password = request.data.get('confirm_password')

        if not old_password or not new_password or not confirm_password:
            return Response({"error": "All fields are required."}, status=status.HTTP_400_BAD_REQUEST)

        if new_password != confirm_password:
            return Response({"error": "New password and confirm password do not match."}, status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({"error": "The new password must be at least 8 characters long."}, status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[A-Za-z]', new_password):
            return Response({"error": "The new password must contain at least one letter."}, status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[\W_]', new_password):
            return Response({"error": "The new password must contain at least one special character."}, status=status.HTTP_400_BAD_REQUEST)

        if not user.check_password(old_password):
            return Response({"error": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        return Response({"message": "Password successfully updated."}, status=status.HTTP_200_OK)

    class ApplicationViewSet(generics.ListAPIView):
        queryset = Application.objects.all()
        serializer_class = ApplicationSerializer
        permission_classes = [IsAdmin]

    class ApproveStudentApplicationAPIView(APIView):
        permission_classes = [IsAdmin]

        def put(self, request, application_id, *args, **kwargs):
            try:
                application = Application.objects.get(id=application_id)
            except Application.DoesNotExist:
                return Response({"error": "Заявка с таким ID не найдена"}, status=status.HTTP_404_NOT_FOUND)

            application.status = "approved"
            additional_notes = request.data.get("notes")
            if additional_notes:
                application.notes = additional_notes

            application.save()

            return Response(
                {"message": "Заявка успешно одобрена", "application_id": application.id},
                status=status.HTTP_200_OK
            )

    class DeleteStudentApplicationAPIView(APIView):
        permission_classes = [IsAdmin]

        def delete(self, request, application_id, *args, **kwargs):
            try:
                application = Application.objects.get(id=application_id)
            except Application.DoesNotExist:
                return Response({"error": "Заявка с таким ID не найдена"}, status=status.HTTP_404_NOT_FOUND)

            application.delete()
            return Response({"message": "Заявка успешно удалена"}, status=status.HTTP_200_OK)
