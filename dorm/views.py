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
from io import BytesIO
import openpyxl
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from .serializers import ApplicationSerializer
from django.views.generic import View
from django.core.mail import send_mail
from django.conf import settings

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


class IsAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        return is_authenticated and (hasattr(request.user, 'admin') or request.user.is_superuser)

class StudentDetailView(RetrieveUpdateAPIView):
    serializer_class = StudentSerializer
    permission_classes = [IsAuthenticated]

    def get_object(self):
        try:
            return self.request.user.student
        except Student.DoesNotExist:
            raise NotFound("Студент с таким токеном не найден.")


class ApplicationDetailView(RetrieveUpdateAPIView):
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer
    permission_classes = [IsAdmin]

    def get(self, request, *args, **kwargs):
        application_id = kwargs.get('pk')
        application = get_object_or_404(Application, id=application_id)

        serialized_data = self.get_serializer(application).data

        file_fields = [
            'payment_screenshot',
            'orphan_certificate',
            'disability_1_2_certificate',
            'disability_3_certificate',
            'parents_disability_certificate',
            'loss_of_breadwinner_certificate',
            'social_aid_certificate',
            'mangilik_el_certificate',
            'olympiad_winner_certificate',
        ]

        serialized_data['files'] = [
            {
                'field_name': field,
                'url': getattr(application, field).url if getattr(application, field) else None,
                'name': getattr(application, field).name if getattr(application, field) else None
            }
            for field in file_fields if getattr(application, field)
        ]

        return Response(serialized_data)



class PDFView(View):
    def get(self, request, pk, field_name):
        application = get_object_or_404(Application, id=pk)
        file = getattr(application, field_name, None)

        if file and file.name.endswith('.pdf'):
            return FileResponse(file.open('rb'), content_type='application/pdf')
        return Response({'error': 'The requested file is not a PDF or does not exist.'}, status=400)





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

        dormitory_name = application.dormitory_choice.name if application.dormitory_choice else "общага"

        if application.status == 'order':
            return Response({"status": f"Поздравляем! Вам выдан ордер в общагу: {dormitory_name}."}, status=status.HTTP_200_OK)

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
                        students_for_room = self.get_students_for_room(grouped_applications, room_size)

                        if not students_for_room:
                            continue

                        room_label = f"{room_number}{room_suffix}"
                        print(f"Комната размером {room_size} в общежитии {dorm.id} получает студентов: ",
                              [student_application.student.id for student_application in students_for_room])

                        for student_application in students_for_room:
                            student_in_dorm = StudentInDorm.objects.create(
                                student_id=student_application.student,
                                dorm_id=dorm,
                                room=room_label,
                                application_id=student_application
                            )

                            student_application.status = 'order'
                            student_application.save()

                            allocated_students.append({
                                "student_email": student_in_dorm.student_id.email,
                                "dorm_name": getattr(student_in_dorm.dorm_id, "name", "Общежитие"),
                                "room": student_in_dorm.room
                            })

                        room_suffix, room_number = self.update_room_label(room_suffix, room_number)

        self.send_emails(allocated_students)

        allocated_count = len(allocated_students)
        print("Общее количество студентов, добавленных в StudentInDorm:", allocated_count)

        return Response(
            {
                "detail": "Студенты успешно распределены по комнатам.",
                "allocated_students": allocated_students
            },
            status=status.HTTP_200_OK
        )

    def get_students_for_room(self, grouped_applications, room_size):

        for test_result, test_group in grouped_applications.items():
            if len(test_group) >= room_size:
                students_for_room = [
                    student for student in test_group[:room_size]
                    if not StudentInDorm.objects.filter(student_id=student.student).exists()
                ]
                grouped_applications[test_result] = [
                    student for student in test_group if student not in students_for_room
                ]
                return students_for_room

        remaining_students = [
            student for group in grouped_applications.values() for student in group
            if not StudentInDorm.objects.filter(student_id=student.student).exists()
        ]
        if remaining_students:
            students_for_room = remaining_students[:room_size]
            for student in students_for_room:
                grouped_applications[student.test_result].remove(student)
            return students_for_room

        return []

    def update_room_label(self, room_suffix, room_number):
        if room_suffix == 'А':
            return 'Б', room_number
        else:
            return 'А', room_number + 1

    def send_emails(self, allocated_students):
        for student in allocated_students:
            if student["student_email"]:
                send_mail(
                    subject="Ордер на заселение в общежитие",
                    message=f"Поздравляем, вам был выдан ордер на заселение в общежитие!\n"
                            f"Общежитие: {student['dorm_name']}\n"
                            f"Комната: {student['room']}",
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[student["student_email"]],
                    fail_silently=False,
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



class ChangeStudentDormitoryAPIView(APIView):
    permission_classes = [IsAdmin]

    def put(self, request, application_id, *args, **kwargs):
        try:
            application = Application.objects.get(id=application_id)
        except Application.DoesNotExist:
            return Response({"error": "Заявка с таким ID не найдена"}, status=status.HTTP_404_NOT_FOUND)

        dormitory_name = request.data.get('dorm_name')
        if not dormitory_name:
            return Response({"error": "Не указано имя общежития"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            dormitory = Dorm.objects.get(name=dormitory_name)
        except Dorm.DoesNotExist:
            return Response({"error": "Общежитие с таким именем не найдено"}, status=status.HTTP_400_BAD_REQUEST)

        application.dormitory_choice = dormitory
        application.save()

        student = application.student
        student_in_dorm, created = StudentInDorm.objects.update_or_create(
            student_id=student,
            application_id=application,
            defaults={
                'dorm_id': dormitory,
                'room': None,
            }
        )

        return Response(
            {
                "message": "Общежитие для студента успешно изменено",
                "application_id": application.id,
                "dormitory_choice": dormitory.name,
                "student_in_dorm_created": created,
            },
            status=status.HTTP_200_OK
        )




class ExportStudentInDormExcelView(APIView):

    permission_classes = [IsAdmin]

    def get(self, request, *args, **kwargs):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Студенты в общежитиях"

        headers = ["S Студента", "Фамилия", "Имя", "Отчество", "Общежитие", "Комната", "ID Заявления", "Ордер"]
        sheet.append(headers)

        students_in_dorm = StudentInDorm.objects.select_related('student_id', 'dorm_id', 'application_id')
        for student_dorm in students_in_dorm:
            student = student_dorm.student_id
            row = [
                getattr(student, 's', "Нет данных"),
                getattr(student, 'last_name', "Нет данных"),
                getattr(student, 'first_name', "Нет данных"),
                getattr(student, 'middle_name', "Нет данных"),
                getattr(student_dorm.dorm_id, 'name', "Нет данных"),
                student_dorm.room or "Нет данных",
                student_dorm.application_id.id if student_dorm.application_id else "Нет данных",
                student_dorm.order.url if student_dorm.order else "Нет"
            ]
            sheet.append(row)

        output = BytesIO()
        workbook.save(output)
        output.seek(0)

        response = HttpResponse(
            output,
            content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )
        response['Content-Disposition'] = 'attachment; filename="students_in_dorm.xlsx"'

        return response