from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import viewsets, status, generics, filters, permissions, request
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
from rest_framework.exceptions import NotFound, PermissionDenied
from django.contrib.auth import authenticate
from django.http import HttpResponse, Http404, JsonResponse
from io import BytesIO
import openpyxl
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.views.generic import View
from django.core.mail import send_mail
from django.conf import settings
from rest_framework.generics import ListAPIView
from django.db.models import F, Case, When, Value, IntegerField, BooleanField
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum
from django.db import transaction
from collections import defaultdict

from rest_framework.permissions import BasePermission
import PyPDF2

from .utils import *


class StudentViewSet(generics.ListAPIView):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer


class RegionListView(generics.ListAPIView):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer

class DormView(generics.ListAPIView):
    queryset = Dorm.objects.all()
    serializer_class = DormSerializer

class TestQuestionViewSet(generics.ListAPIView):
    queryset = TestQuestion.objects.all()
    serializer_class = TestQuestionSerializer


class ApplicationViewSet(generics.ListAPIView):
    queryset = Application.objects.all().prefetch_related('evidences')
    serializer_class = ApplicationSerializer


class IsAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        return is_authenticated and (hasattr(request.user, 'admin') or request.user.is_superuser)


class IsStudentOrAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        if not is_authenticated:
            return False

        is_student = hasattr(request.user, 'student')
        is_admin = request.user.is_staff or request.user.is_superuser

        return is_student or is_admin


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
    def get(self, request, pk, evidence_code):
        """
        Возвращает PDF-файл для заявки с id=pk и типом доказательства, равным evidence_code.
        """
        application_evidence = get_object_or_404(
            ApplicationEvidence,
            application__id=pk,
            evidence_type__code=evidence_code
        )
        file_field = application_evidence.file
        if file_field and file_field.name.lower().endswith('.pdf'):
            return FileResponse(file_field.open('rb'), content_type='application/pdf')
        return JsonResponse({'error': 'Запрошенный файл не является PDF или не существует.'}, status=400)



class PaymentScreenshotView(View):
    def get(self, request, pk):
        application = get_object_or_404(Application, id=pk)
        file = application.payment_screenshot

        if file and file.name.endswith('.pdf'):
            return FileResponse(file.open('rb'), content_type='application/pdf')
        raise Http404("Скрин оплаты не найден или формат файла не поддерживается.")





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
                        'phone_number': row['phone_number'],
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


class DormCostListView(APIView):
    def get(self, request):
        costs = Dorm.objects.values_list('cost', flat=True).distinct()
        return Response(sorted(costs), status=status.HTTP_200_OK)




def extract_text_from_pdf(file_obj):
    """
    Извлекает текст из PDF-файла с помощью PyPDF2.
    Если возникает ошибка при чтении, возвращается пустая строка.
    """
    text = ""
    try:
        reader = PyPDF2.PdfReader(file_obj)
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text += page_text
    except Exception as e:
        text = ""
    return text

class CreateApplicationView(APIView):
    permission_classes = [IsStudent]

    def post(self, request):
        student_id = request.user.student.id
        dormitory_cost = request.data.get('dormitory_cost')

        if not student_id:
            return Response({"error": "Поле 'student' обязательно"}, status=status.HTTP_400_BAD_REQUEST)

        if not dormitory_cost:
            return Response({"error": "Поле 'dormitory_cost' обязательно"}, status=status.HTTP_400_BAD_REQUEST)

        if not Dorm.objects.filter(cost=dormitory_cost).exists():
            return Response({"error": "Общежитий с выбранной стоимостью не найдено"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            return Response({"error": "Студент с таким ID не найден"}, status=status.HTTP_400_BAD_REQUEST)

        evidences_files = request.FILES
        # Проверка MIME-типа каждого файла
        for key in evidences_files:
            file = evidences_files.get(key)
            if file and file.content_type != 'application/pdf':
                return Response(
                    {"error": f"Файл в поле '{key}' должен быть формата PDF."},
                    status=status.HTTP_400_BAD_REQUEST
                )

        serializer = ApplicationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    application = serializer.save(student=student, dormitory_cost=dormitory_cost)
                    for key, file in request.FILES.items():
                        try:
                            evidence_type = EvidenceType.objects.get(code=key)
                        except EvidenceType.DoesNotExist:
                            continue  # Если evidence type не найден, пропускаем

                        # Извлекаем текст из PDF-файла
                        extracted_text = extract_text_from_pdf(file)
                        # Сброс указателя файла для корректного сохранения
                        file.seek(0)
                        keywords = evidence_type.keywords.all()
                        # Если для типа справки заданы ключевые слова, проверяем их наличие в тексте
                        if keywords and not any(
                            keyword.keyword.lower() in extracted_text.lower() for keyword in keywords
                        ):
                            raise ValidationError(
                                f"Загруженный файл для '{evidence_type.name}' не содержит необходимых ключевых слов."
                            )

                        ApplicationEvidence.objects.create(
                            application=application,
                            evidence_type=evidence_type,
                            file=file
                        )
                return Response(
                    {"message": "Заявка создана", "application_id": application.id},
                    status=status.HTTP_201_CREATED
                )
            except ValidationError as e:
                # Откат транзакции произойдет автоматически при выбросе исключения
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)
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


# для получения уведомлений для администратора
class AdminNotificationListView(APIView):
    permission_classes = [IsAdmin]  # или свой кастомный пермишн

    def get(self, request):
        # Предполагаем, что recipient=текущий пользователь-админ
        notifications = Notification.objects.filter(recipient=request.user, is_read=False)
        # или, если хотите все: .filter(recipient=request.user)

        # Можно добавить пагинацию, но для примера вернем целиком
        data = [{
            "id": n.id,
            "message": n.message,
            "created_at": n.created_at.isoformat()
        } for n in notifications]
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        # Отметить уведомления как прочитанные
        ids = request.data.get('notification_ids', [])
        Notification.objects.filter(pk__in=ids, recipient=request.user).update(is_read=True)
        return Response({"detail": "Отмечены прочитанными"}, status=status.HTTP_200_OK)

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        # Возвращаем только уведомления для этого пользователя,
        # которые не прочитаны
        notifications = Notification.objects.filter(recipient=request.user, is_read=False)
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        # Помечаем уведомления как прочитанные
        notification_ids = request.data.get('notification_ids', [])
        Notification.objects.filter(pk__in=notification_ids, recipient=request.user).update(is_read=True)
        return Response({"detail": "Уведомления помечены как прочитанные"}, status=status.HTTP_200_OK)


# Вью для пометки уведомления как прочитанного
class MarkNotificationAsReadView(generics.UpdateAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAdmin]

    def update(self, request, *args, **kwargs):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"status": "Уведомление отмечено как прочитанное"}, status=status.HTTP_200_OK)


# --- Вопросы ---
class QuestionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Поиск в модели QuestionAnswer (FAQ). Если есть вопрос — возвращаем список ответов,
           иначе пустой список."""
        search_query = request.query_params.get('search', '')
        if search_query:
            answers = QuestionAnswer.objects.filter(question__icontains=search_query)
            if answers.exists():
                data = [{"question": ans.question, "answer": ans.answer} for ans in answers]
                return Response(data, status=status.HTTP_200_OK)
            return Response([], status=status.HTTP_200_OK)
        return Response([], status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
        """Если вопрос есть в базе, сразу возвращаем answer.
           Иначе создаём (или получаем) активный чат и отправляем вопрос админу."""
        question = request.data.get('text')
        student = request.user

        if not question:
            return Response({"error": "Вопрос не может быть пустым"}, status=status.HTTP_400_BAD_REQUEST)

        try:
            qa = QuestionAnswer.objects.get(question__icontains=question)
            return Response({"answer": qa.answer}, status=status.HTTP_200_OK)
        except ObjectDoesNotExist:
            chat, created = Chat.objects.get_or_create(
                student=student,
                is_active=True,
                defaults={'status': 'waiting_for_admin'}
            )
            Message.objects.create(chat=chat, sender=student, content=question)
            # тут можно создать Notification для админа, отправить через channels
            return Response({"message": "Вопрос отправлен администратору"}, status=status.HTTP_201_CREATED)# --- Чаты ---


class CreateChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        """Ищем активный чат для данного студента. Если нет — создаём новый."""
        student = request.user
        active_chat = Chat.objects.filter(student=student, is_active=True).first()
        if active_chat:
            return Response({"id": active_chat.id}, status=status.HTTP_200_OK)

        new_chat = Chat.objects.create(student=student, is_active=True, status='waiting_for_admin')
        return Response({"id": new_chat.id}, status=status.HTTP_201_CREATED)


class StudentChatListView(generics.ListAPIView):
    serializer_class = ChatSerializer
    permission_classes = [IsStudent]

    def get_queryset(self):
        # Студент видит только свои активные чаты
        return Chat.objects.filter(student=self.request.user, is_active=True)

class AdminChatListView(generics.ListAPIView):
    serializer_class = ChatSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        # Администратор видит все активные чаты студентов
        return Chat.objects.filter(is_active=True).order_by('-created_at')

# --- Сообщения ---

class MessageListView(APIView):
    permission_classes = [IsStudentOrAdmin]

    def get(self, request, chat_id):
        chat = get_object_or_404(Chat, id=chat_id, is_active=True)

        if request.user.is_staff or request.user.is_superuser:
            pass
        else:
            if hasattr(request.user, 'student') and chat.student.id != request.user.id:
                return Response({"error": "Нет доступа к этому чату."}, status=status.HTTP_403_FORBIDDEN)

        messages = Message.objects.filter(chat=chat).order_by('timestamp')
        serializer = MessageSerializer(messages, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ChatListView(APIView):
    permission_classes = [IsStudentOrAdmin]

    def get(self, request):
        # Возвращаем только активные чаты;
        # т.к. связь один к одному – каждый чат уникален для студента
        chats = Chat.objects.filter(is_active=True)
        serializer = ChatSerializer(chats, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

class SendMessageView(APIView):
    permission_classes = [IsStudentOrAdmin]

    def post(self, request, chat_id):
        chat = get_object_or_404(Chat, id=chat_id, is_active=True)
        text = request.data.get('text')
        if not text:
            return Response({"error": "Сообщение не может быть пустым"}, status=status.HTTP_400_BAD_REQUEST)

        receiver = chat.student if request.user.is_staff else User.objects.filter(is_staff=True).first()

        Message.objects.create(chat=chat, sender=request.user, receiver=receiver, content=text)

        Notification.objects.create(recipient=receiver, message=f"Новое сообщение: {text[:50]}")

        return Response({"status": "Сообщение отправлено"}, status=status.HTTP_201_CREATED)

class EndChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, chat_id):
        """Помечаем чат как неактивный, если пользователь - владелец или админ."""
        chat = get_object_or_404(Chat, id=chat_id, is_active=True)
        if request.user.is_staff or chat.student == request.user:
            chat.is_active = False
            chat.status = 'closed'
            chat.save()
            return Response({"status": "Чат завершён"}, status=status.HTTP_200_OK)
        return Response({"error": "Нет доступа к этому чату."}, status=status.HTTP_403_FORBIDDEN)
# --- Запрос оператора ---

class RequestAdminView(APIView):
    permission_classes = [IsStudent]  # Только студент может запросить оператора
    def post(self, request):
        chat_id = request.data.get('chat_id')
        chat = get_object_or_404(Chat, id=chat_id, is_active=True, student=request.user)
        admin = get_object_or_404(User, is_staff=True)
        Notification.objects.create(
            recipient=admin,
            message=f"Студент {(request.user.username if hasattr(request.user, 'username') else request.user.s)[:50]} просит подключить оператора к чату #{chat.id}"
        )
        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "admin_notifications",
            {
                "type": "new_chat",
                "chat_id": chat.id,
                "student": request.user.username if hasattr(request.user, 'username') else request.user.s,
                "question": "Запрос оператора"
            }
        )
        return Response({"status": "Оператор уведомлен"}, status=status.HTTP_200_OK)




class UpdateEvidenceStatusAPIView(APIView):
    # Здесь можно добавить permission_classes для админа
    def put(self, request, pk):
        try:
            evidence = ApplicationEvidence.objects.get(pk=pk)
        except ApplicationEvidence.DoesNotExist:
            return Response({"error": "Справка не найдена."}, status=status.HTTP_404_NOT_FOUND)
        approved = request.data.get('approved')
        if approved is None:
            return Response({"error": "Поле 'approved' обязательно."}, status=status.HTTP_400_BAD_REQUEST)
        evidence.approved = approved
        evidence.save()
        return Response({"message": "Статус справки обновлен."}, status=status.HTTP_200_OK)

class EvidenceTypeListAPIView(ListAPIView):
    queryset = EvidenceType.objects.all()
    serializer_class = EvidenceTypeSerializer





# class DistributeStudentsAPIView(APIView):
#     permission_classes = [IsAdmin]
#
#     def post(self, request, *args, **kwargs):
#         total_places = Dorm.objects.aggregate(total_places=models.Sum('total_places'))['total_places']
#
#         if not total_places or total_places <= 0:
#             return Response({"detail": "Нет доступных мест в общежитиях."}, status=status.HTTP_400_BAD_REQUEST)
#
#         pending_applications = Application.objects.filter(
#             approval=False, status="pending"
#         ).select_related('student').prefetch_related('evidences')
#
#         # Сортируем заявки на основе вычисленного балла
#         sorted_applications = sorted(
#             pending_applications,
#             key=lambda app: calculate_application_score(app),
#             reverse=True
#         )
#
#         selected_applications = sorted_applications[:total_places]
#         rejected_applications = sorted_applications[total_places:]
#
#         approved_students = []
#
#         with transaction.atomic():
#             for application in selected_applications:
#                 application.approval = True
#                 application.status = "awaiting_payment"
#                 application.save()
#                 approved_students.append({
#                     "student_s": getattr(application.student, "s", "Нет S"),
#                     "first_name": getattr(application.student, 'first_name', 'Нет имени'),
#                     "last_name": getattr(application.student, 'last_name', 'Нет имени'),
#                     "course": getattr(application.student, 'course', 'Не указан'),
#                     "ent_result": application.ent_result,
#                     "gpa": application.gpa,
#                 })
#
#             for application in rejected_applications:
#                 application.status = "rejected"
#                 application.save()
#
#         return Response(
#             {
#                 "detail": f"{len(selected_applications)} студентов были одобрены для заселения.",
#                 "approved_students": approved_students
#             },
#             status=status.HTTP_200_OK
#         )



# Первый эндпоинт: формирование списка для проверки администратором

class GenerateSelectionAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        total_places = Dorm.objects.aggregate(total_places=models.Sum('total_places'))['total_places']

        if not total_places or total_places <= 0:
            return Response(
                {"detail": "Нет доступных мест в общежитиях."},
                status=status.HTTP_400_BAD_REQUEST
            )

        pending_applications = Application.objects.filter(
            approval=False, status="pending"
        ).select_related('student').prefetch_related('evidences')

        # Сортируем заявки на основе вычисленного балла
        sorted_applications = sorted(
            pending_applications,
            key=lambda app: calculate_application_score(app),
            reverse=True
        )

        selected_applications = sorted_applications[:total_places]
        rejected_applications = sorted_applications[total_places:]

        approved_students = []

        with transaction.atomic():
            # Отмечаем выбранные заявки как "approved" для дальнейшего подтверждения
            for application in selected_applications:
                application.approval = True
                application.status = "approved"  # статус для ручного контроля
                application.save()
                approved_students.append({
                    "student_s": getattr(application.student, "s", "Нет S"),
                    "first_name": getattr(application.student, 'first_name', 'Нет имени'),
                    "last_name": getattr(application.student, 'last_name', 'Нет имени'),
                    "course": getattr(application.student, 'course', 'Не указан'),
                    "ent_result": application.ent_result,
                    "gpa": application.gpa,
                })

            # Отмечаем остальные заявки как отклонённые
            for application in rejected_applications:
                application.status = "rejected"
                application.save()

        return Response(
            {
                "detail": f"Сформирован список: {len(selected_applications)} заявок одобрено для проверки, {len(rejected_applications)} заявок отклонено.",
                "approved_students": approved_students
            },
            status=status.HTTP_200_OK
        )









# Второй эндпоинт: перевод одобренных заявок в статус "awaiting_payment" и уведомление студентов



class NotifyApprovedStudentsAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        # Получаем все одобренные заявки для уведомления
        approved_applications = list(Application.objects.filter(
            approval=True, status="approved"
        ))

        # Вычисляем вместимость общаг по стоимости: группируем Dorm по cost
        dorm_capacities = Dorm.objects.values('cost').annotate(total_capacity=Sum('total_places'))
        capacity_by_cost = {entry['cost']: entry['total_capacity'] for entry in dorm_capacities}

        # Группируем заявки по dormitory_cost
        apps_by_cost = defaultdict(list)
        for app in approved_applications:
            apps_by_cost[app.dormitory_cost].append(app)

        # Сортируем стоимости по убыванию (например, [800000, 400000])
        sorted_costs = sorted(capacity_by_cost.keys(), reverse=True)

        transferred_app_ids = []

        # Для каждой группы, начиная с самой высокой стоимости, пытаемся перевести избыток заявок в группу с более низкой стоимостью
        for i in range(len(sorted_costs) - 1):
            cost = sorted_costs[i]
            next_cost = sorted_costs[i + 1]
            current_apps = apps_by_cost[cost]
            capacity = capacity_by_cost.get(cost, 0)
            overflow = len(current_apps) - capacity

            if overflow > 0:
                # Определяем свободные места в группе со следующей (более низкой) стоимостью
                next_capacity = capacity_by_cost.get(next_cost, 0)
                current_next_count = len(apps_by_cost[next_cost])
                available_lower = next_capacity - current_next_count

                to_transfer_count = min(overflow, available_lower) if available_lower > 0 else 0

                if to_transfer_count > 0:
                    # Сортируем заявки в группе с данной стоимостью по возрастанию балла (наименьший балл – первый)
                    current_apps_sorted = sorted(current_apps, key=lambda app: calculate_application_score(app))
                    apps_to_transfer = current_apps_sorted[:to_transfer_count]

                    for app in apps_to_transfer:
                        # Переносим студента: меняем стоимость на следующую
                        old_cost = app.dormitory_cost
                        app.dormitory_cost = next_cost
                        app.save()
                        send_email_notification(
                            app.student.email,
                            f"Здравствуйте, {app.student.first_name}! К сожалению, вам не было предоставлено место за {old_cost}. Вместо этого предоставляем место за {next_cost}."
                        )
                        transferred_app_ids.append(app.id)
                        # Обновляем группы заявок
                        apps_by_cost[cost].remove(app)
                        apps_by_cost[next_cost].append(app)

        # После перераспределения устанавливаем статус "awaiting_payment" для всех заявок и отправляем уведомления
        with transaction.atomic():
            for app in approved_applications:
                app.status = "awaiting_payment"
                app.save()
                if app.id not in transferred_app_ids:
                    send_email_notification(
                        app.student.email,
                        f"Здравствуйте, {app.student.first_name}! Вам было выделено место в общежитии. Просим вас внести оплату за предоставленное место."
                    )

        count = len(approved_applications)
        return Response(
            {
                "detail": f"Уведомление отправлено {count} одобренным студентам. {len(transferred_app_ids)} студентов были переведены в общагу с меньшей стоимостью."
            },
            status=status.HTTP_200_OK
        )





class DistributeStudentsAPIView2(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        # Загружаем Excel‑файл, переданный администратором
        excel_file = request.FILES.get('excel_file')
        if not excel_file:
            return Response(
                {"detail": "Excel‑файл обязателен для проверки данных студентов."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            return Response(
                {"detail": f"Ошибка при чтении Excel‑файла: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Формируем словарь валидных студентов из Excel‑файла.
        # Ключ – кортеж (first_name, last_name, middle_name, phone_number),
        # значение – сумма из файла (sum)
        valid_students = {}
        for index, row in df.iterrows():
            key = (
                row['first_name'].strip() if isinstance(row['first_name'], str) else row['first_name'],
                row['last_name'].strip() if isinstance(row['last_name'], str) else row['last_name'],
                row['middle_name'].strip() if isinstance(row['middle_name'], str) else row['middle_name'],
                str(row['phone_number']).strip()
            )
            valid_students[key] = row['sum']

        print("Отладка: Содержимое словаря valid_students:")
        for key, value in valid_students.items():
            print(f"{key} : {value}")

        # Получаем заявки, у которых одобрено и есть скрин оплаты
        approved_applications_all = Application.objects.filter(
            approval=True,
            payment_screenshot__isnull=False
        ).exclude(payment_screenshot="")

        approved_applications = []
        for app in approved_applications_all:
            student = app.student
            key = (
                student.first_name.strip() if student.first_name and isinstance(student.first_name, str) else student.first_name,
                student.last_name.strip() if student.last_name and isinstance(student.last_name, str) else student.last_name,
                student.middle_name.strip() if student.middle_name and isinstance(student.middle_name, str) else student.middle_name,
                str(student.phone_number).strip()
            )
            if key in valid_students:
                excel_sum = valid_students[key]
                # Сравнение суммы из Excel с dormitory_cost из заявки
                if excel_sum == app.dormitory_cost:
                    app.is_full_payment = True
                elif excel_sum == (app.dormitory_cost / 2):
                    app.is_full_payment = False
                else:
                    app.is_full_payment = None  # Неопределено
                app.save()
                approved_applications.append(app)
                print(f"Отладка: Обновлена заявка {app.id}. is_full_payment={app.is_full_payment} "
                      f"(Excel sum: {excel_sum}, dormitory_cost: {app.dormitory_cost})")
            else:
                print(f"Отладка: Для заявки {app.id} ключ {key} не найден в valid_students.")

        # Группируем заявки по результату теста
        grouped_applications = defaultdict(list)
        for app in approved_applications:
            grouped_applications[app.test_result].append(app)

        dorms = Dorm.objects.all()

        print("Общее количество одобренных заявок с оплатой и в списке из Excel:", len(approved_applications))
        for test_result, apps in grouped_applications.items():
            print(f"Количество студентов с результатом теста '{test_result}': {len(apps)}")

        allocated_students = []

        with transaction.atomic():
            for dorm in dorms:
                print("Отладка: Обрабатываем общежитие", dorm.id, getattr(dorm, 'name', ''))
                room_counts = {
                    2: dorm.rooms_for_two,
                    3: dorm.rooms_for_three,
                    4: dorm.rooms_for_four
                }
                room_number = 101
                room_suffix = 'А'
                for room_size, available_rooms in room_counts.items():
                    print(f"Отладка: Обработка комнат размера {room_size}, available_rooms: {available_rooms}")
                    for _ in range(available_rooms):
                        students_for_room = self.get_students_for_room(grouped_applications, room_size)
                        if not students_for_room:
                            print("Отладка: Нет студентов для комнаты размера", room_size)
                            continue
                        room_label = f"{room_number}{room_suffix}"
                        print(f"Отладка: Комната {room_label} получает студентов: ",
                              [student_application.student.id for student_application in students_for_room])
                        for student_application in students_for_room:
                            # Обновление статуса заявки на 'order'
                            student_application.status = 'order'
                            student_application.save()
                            print(f"Отладка: Обновлен статус заявки {student_application.id} на 'order'")

                            student_in_dorm = StudentInDorm.objects.create(
                                student_id=student_application.student,
                                dorm_id=dorm,
                                room=room_label,
                                application_id=student_application
                            )
                            allocated_students.append({
                                "student_email": student_in_dorm.student_id.email,
                                "dorm_name": getattr(student_in_dorm.dorm_id, "name", "Общежитие"),
                                "room": student_in_dorm.room
                            })
                        room_suffix, room_number = self.update_room_label(room_suffix, room_number)

        print("Отладка: Начинается отправка писем")
        self.send_emails(allocated_students)

        allocated_count = len(allocated_students)
        print("Отладка: Общее количество студентов, добавленных в StudentInDorm:", allocated_count)

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
                print(f"Отладка: Отправка письма на {student['student_email']}")
                try:
                    result = send_mail(
                        subject="Ордер на заселение в общежитие",
                        message=(
                            f"Поздравляем, вам был выдан ордер на заселение в общежитие!\n"
                            f"Общежитие: {student['dorm_name']}\n"
                            f"Комната: {student['room']}"
                        ),
                        from_email=settings.EMAIL_HOST_USER,
                        recipient_list=[student["student_email"]],
                        fail_silently=False,
                    )
                    print(f"Отладка: Результат отправки письма: {result}")
                except Exception as e:
                    print(f"Отладка: Ошибка при отправке письма на {student['student_email']}: {e}")





class SendPartialPaymentReminderAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        # Фильтруем заявки:
        # выбираем те, у которых:
        # 1. Заявка одобрена и есть скрин оплаты
        # 2. Полная оплата ещё не произведена (is_full_payment=False)
        partial_applications = Application.objects.filter(
            approval=True,
            payment_screenshot__isnull=False
        ).exclude(payment_screenshot="").filter(
            is_full_payment=False  # Новое булево поле, которое должно быть обновлено при получении полной оплаты
        )

        reminded_emails = []

        for app in partial_applications:
            student_email = app.student.email
            # Можно добавить детали: например, сколько осталось доплатить (если известны расчёты)
            message = (
                f"Уважаемый(ая) {app.student.first_name} {app.student.last_name},\n\n"
                "Наша система показывает, что Вы внесли частичную оплату за общежитие. "
                "Пожалуйста, обратите внимание, что необходимо внести оставшуюся сумму до установленного срока.\n\n"
                "С уважением, администрация."
            )

            try:
                result = send_mail(
                    subject="Напоминание о полной оплате общежития",
                    message=message,
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[student_email],
                    fail_silently=False,
                )
                reminded_emails.append(student_email)
                print(f"Отладка: Письмо отправлено на {student_email}, результат: {result}")
            except Exception as e:
                print(f"Отладка: Ошибка при отправке письма на {student_email}: {e}")

        return Response(
            {
                "detail": "Напоминания отправлены студентам с частичной оплатой.",
                "reminded_emails": reminded_emails
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



class RejectStudentApplicationAPIView(APIView):
    permission_classes = [IsAdmin]

    def put(self, request, application_id, *args, **kwargs):
        try:
            application = Application.objects.get(id=application_id)
        except Application.DoesNotExist:
            return Response({"error": "Заявка с таким ID не найдена"}, status=status.HTTP_404_NOT_FOUND)

        application.status = "rejected"
        additional_notes = request.data.get("notes")
        if additional_notes:
            application.notes = additional_notes

        application.save()

        return Response(
            {"message": "Заявка успешно отклонена", "application_id": application.id},
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



class DormsViewSet(viewsets.ModelViewSet):
    queryset = Dorm.objects.all()
    serializer_class = DormSerializer
    # permission_classes = [IsAdmin]




class StudentsViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer
    # permission_classes = [IsAdmin]

    def perform_create(self, serializer):
        s_value = serializer.validated_data.get('s')
        if Student.objects.filter(s=s_value).exists():
            raise ValidationError(f"Student with s = {s_value} already exists.")

        serializer.save()



class ApplicationListView(ListAPIView):
    serializer_class = ApplicationSerializer

    def get_queryset(self):
        queryset = Application.objects.select_related('student')
        ordering = self.request.query_params.get('ordering', 'priority')

        if ordering == 'gpa':
            queryset = queryset.annotate(
                sort_key=Case(
                    When(student__course="1", then=F('ent_result')),
                    default=F('gpa'),
                    output_field=IntegerField()
                )
            ).order_by(
                Case(When(student__course="1", then=Value(1)), default=Value(0)).asc(),
                F('sort_key').desc()
            )

        elif ordering == 'ent':
            queryset = queryset.annotate(
                sort_key=Case(
                    When(student__course="1", then=F('ent_result')),
                    default=F('gpa'),
                    output_field=IntegerField()
                )
            ).order_by(
                Case(When(student__course="1", then=Value(0)), default=Value(1)),
                F('sort_key').desc()
            )

        else:  # Default sorting by priority
            queryset = queryset.annotate(
                orphan=Case(
                    When(orphan_certificate__isnull=False, then=Value(True)),
                    When(disability_1_2_certificate__isnull=False, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField()
                ),
                social=Case(
                    When(disability_3_certificate__isnull=False, then=Value(True)),
                    When(parents_disability_certificate__isnull=False, then=Value(True)),
                    When(loss_of_breadwinner_certificate__isnull=False, then=Value(True)),
                    When(social_aid_certificate__isnull=False, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField()
                ),
                mangilik=Case(
                    When(mangilik_el_certificate__isnull=False, then=Value(True)),
                    default=Value(False),
                    output_field=BooleanField()
                ),
                olympiad=Case(
                    When(student__course="1", olympiad_winner_certificate__isnull=False, then=Value(1)),
                    default=Value(0),
                    output_field=IntegerField()
                ),
                ent_result_value=Case(
                    When(student__course="1", then=F('ent_result')),
                    default=Value(0),
                    output_field=IntegerField()
                ),
                gpa_value=Case(
                    When(student__course__gt="1", then=F('gpa')),
                    default=Value(0),
                    output_field=IntegerField()
                )
            ).order_by(
                '-orphan',
                '-social',
                '-mangilik',
                '-olympiad',
                '-ent_result_value',
                '-gpa_value',
                'id'
            )

        return queryset
