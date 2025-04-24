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
import json

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


class DormImageView(generics.ListAPIView):
    queryset = DormImage.objects.all()
    serializer_class = DormImageSerializer


class StudentInDormView(generics.ListAPIView):
    queryset = StudentInDorm.objects.all()
    serializer_class = StudentInDormSerializer

class TestQuestionViewSet(generics.ListAPIView):
    queryset = TestQuestion.objects.all()
    serializer_class = TestQuestionSerializer


class ApplicationViewSet(generics.ListAPIView):
    queryset = Application.objects.all().prefetch_related('evidences')
    serializer_class = ApplicationSerializer


class KnowledgeBaseListView(generics.ListAPIView):
    queryset = KnowledgeBase.objects.all()
    serializer_class = KnowledgeBaseSerializer
    permission_classes = [permissions.IsAdminUser]

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


class AdminNotificationListView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request):
        notifications = Notification.objects.filter(recipient=request.user, is_read=False)

        data = [{
            "id": n.id,
            "message": n.message,
            "created_at": n.created_at.isoformat()
        } for n in notifications]
        return Response(data, status=status.HTTP_200_OK)

    def post(self, request):
        ids = request.data.get('notification_ids', [])
        Notification.objects.filter(pk__in=ids, recipient=request.user).update(is_read=True)
        return Response({"detail": "Отмечены прочитанными"}, status=status.HTTP_200_OK)

class NotificationListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        notifications = Notification.objects.filter(recipient=request.user, is_read=False)
        serializer = NotificationSerializer(notifications, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        notification_ids = request.data.get('notification_ids', [])
        Notification.objects.filter(pk__in=notification_ids, recipient=request.user).update(is_read=True)
        return Response({"detail": "Уведомления помечены как прочитанные"}, status=status.HTTP_200_OK)


class MarkNotificationAsReadView(generics.UpdateAPIView):
    serializer_class = NotificationSerializer
    permission_classes = [IsAdmin]

    def update(self, request, *args, **kwargs):
        notification = self.get_object()
        notification.is_read = True
        notification.save()
        return Response({"status": "Уведомление отмечено как прочитанное"}, status=status.HTTP_200_OK)


class QuestionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        search_query = request.query_params.get('search', '')
        if search_query:
            answers = QuestionAnswer.objects.filter(question__icontains=search_query)
            if answers.exists():
                data = [{"question": ans.question, "answer": ans.answer} for ans in answers]
                return Response(data, status=status.HTTP_200_OK)
            return Response([], status=status.HTTP_200_OK)
        return Response([], status=status.HTTP_400_BAD_REQUEST)

    def post(self, request):
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
            return Response({"message": "Вопрос отправлен администратору"}, status=status.HTTP_201_CREATED)# --- Чаты ---


class CreateChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
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
        return Chat.objects.filter(student=self.request.user, is_active=True)

class AdminChatListView(generics.ListAPIView):
    serializer_class = ChatSerializer
    permission_classes = [IsAdmin]

    def get_queryset(self):
        return Chat.objects.filter(is_active=True).order_by('-created_at')


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

        sender = request.user
        receiver = chat.student if sender.is_staff else User.objects.filter(is_staff=True).first()

        # Сохраняем сообщение от студента/админа
        Message.objects.create(chat=chat, sender=sender, receiver=receiver, content=text)

        # Если это студент — запускаем AI
        if not sender.is_staff:
            ai_answer = find_best_answer(text)

            if ai_answer and "не знаю" not in ai_answer.lower():
                # AI нашёл ответ — отправляем его от имени "бота"
                bot_user = User.objects.filter(s="F22016183").first()
                if not bot_user:
                    bot_user = User.objects.create(username="DormMateBot", is_staff=True)
                Message.objects.create(chat=chat, sender=bot_user, receiver=sender, content=ai_answer)
                return Response({"status": "Ответ сгенерирован ботом"}, status=status.HTTP_201_CREATED)

            else:
                # AI не нашёл ответ — уведомляем админа
                admin = User.objects.filter(is_staff=True).first()
                Notification.objects.create(
                    recipient=admin,
                    message=f"Новый вопрос в чате #{chat.id}, требуется участие оператора."
                )

                channel_layer = get_channel_layer()
                async_to_sync(channel_layer.group_send)(
                    "admin_notifications",
                    {
                        "type": "new_chat",
                        "chat_id": chat.id,
                        "student": sender.username,
                        "question": text
                    }
                )

                Message.objects.create(
                    chat=chat,
                    sender=None,  # Можно использовать специального "системного" пользователя
                    receiver=sender,
                    content="Спасибо за вопрос! Наш оператор скоро подключится к чату и поможет вам."
                )

                return Response({"status": "Оператор уведомлён, бот не смог ответить"}, status=status.HTTP_200_OK)

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

class RequestAdminView(APIView):
    permission_classes = [IsStudent]
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






class PaymentConfirmationAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        # 1. Загрузка и валидация Excel‑файла
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

        # Формирование словаря валидных студентов:
        # ключ – (first_name, last_name, middle_name, phone_number)
        valid_students = {}
        for index, row in df.iterrows():
            key = (
                row['first_name'].strip() if isinstance(row['first_name'], str) else row['first_name'],
                row['last_name'].strip() if isinstance(row['last_name'], str) else row['last_name'],
                row['middle_name'].strip() if isinstance(row['middle_name'], str) else row['middle_name'],
                str(row['phone_number']).strip()
            )
            valid_students[key] = row['sum']

        # 2. Получение одобренных заявок с наличием скрина оплаты
        approved_applications_all = Application.objects.filter(
            approval=True,
            payment_screenshot__isnull=False
        ).exclude(payment_screenshot="")

        added_students = []
        with transaction.atomic():
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
                    if excel_sum == app.dormitory_cost:
                        app.is_full_payment = True
                    elif excel_sum == (app.dormitory_cost / 2):
                        app.is_full_payment = False
                    else:
                        app.is_full_payment = None
                    app.save()

                    # Если оплата подтверждена (значение не None),
                    # создаём запись в StudentInDorm без выбора общаги – распределение останется во второй вьюшке.
                    if app.is_full_payment is not None:
                        # Создадим запись, оставив dorm_id незаполненным (при условии, что поле допускает null)
                        # и статус оставим "waiting_order"
                        if not StudentInDorm.objects.filter(student_id=app.student, application_id=app).exists():
                            StudentInDorm.objects.create(
                                student_id=app.student,
                                dorm_id=None,
                                group=None,        # группа не назначена
                                application_id=app,
                                status='waiting_order'
                            )
                            added_students.append({
                                "student_email": student.email,
                                "application_id": app.id
                            })

        return Response(
            {
                "detail": "Оплата подтверждена. Студенты добавлены в StudentInDorm с статусом 'waiting_order'.",
                "added_students": added_students
            },
            status=status.HTTP_200_OK
        )






class DistributeStudentsAPIView2(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        # Выбираем записи из StudentInDorm, у которых статус = 'waiting_order'
        # и dorm_id ещё не назначен.
        pending_records = StudentInDorm.objects.filter(status='waiting_order', dorm_id__isnull=True)
        if not pending_records.exists():
            return Response(
                {"detail": "Нет студентов, ожидающих распределения по общежитиям."},
                status=status.HTTP_200_OK
            )

        # Группируем записи по стоимости общежития (берём стоимость из заявки)
        cost_to_records = defaultdict(list)
        for record in pending_records:
            cost = record.application_id.dormitory_cost
            cost_to_records[cost].append(record)

        allocated_students = []
        global_group_counter = 1  # счетчик для уникальных номеров групп

        with transaction.atomic():
            for cost, records in cost_to_records.items():
                # Получаем общежития, соответствующие стоимости
                dorms_for_cost = Dorm.objects.filter(cost=cost)
                if not dorms_for_cost.exists():
                    continue

                # Для распределения можно перебрать общежития по очереди
                # (пример ниже использует первое найденное; при желании можно распределять равномерно)
                for dorm in dorms_for_cost:
                    # Формируем список слотов (комнат) согласно настройкам общежития
                    room_slots = []
                    room_slots.extend([2] * (dorm.rooms_for_two or 0))
                    room_slots.extend([3] * (dorm.rooms_for_three or 0))
                    room_slots.extend([4] * (dorm.rooms_for_four or 0))
                    if not room_slots:
                        continue

                    # Отбираем записи для распределения – только те, которые ещё не получили общагу
                    remaining_records = [rec for rec in records if rec.dorm_id is None]
                    if not remaining_records:
                        continue

                    # Разбиваем записи по полу
                    male_records = [rec for rec in remaining_records if rec.student_id.gender and rec.student_id.gender.upper() == 'M']
                    female_records = [rec for rec in remaining_records if rec.student_id.gender and rec.student_id.gender.upper() == 'F']

                    for slot_size in sorted(room_slots):
                        candidate_pool = None
                        chosen_gender = None
                        if len(male_records) >= slot_size and len(female_records) >= slot_size:
                            if len(male_records) >= len(female_records):
                                candidate_pool = male_records
                                chosen_gender = 'M'
                            else:
                                candidate_pool = female_records
                                chosen_gender = 'F'
                        elif len(male_records) >= slot_size:
                            candidate_pool = male_records
                            chosen_gender = 'M'
                        elif len(female_records) >= slot_size:
                            candidate_pool = female_records
                            chosen_gender = 'F'
                        else:
                            continue

                        allocated_group = self.allocate_slot(candidate_pool, slot_size)
                        if not allocated_group:
                            continue

                        for rec in allocated_group:
                            if chosen_gender == 'M' and rec in male_records:
                                male_records.remove(rec)
                            elif chosen_gender == 'F' and rec in female_records:
                                female_records.remove(rec)
                            # Назначаем данному студенту выбранное общежитие и группу
                            rec.dorm_id = dorm
                            rec.group = str(global_group_counter)
                            # Статус остаётся "waiting_order"
                            rec.save()
                            allocated_students.append({
                                "student_email": rec.student_id.email,
                                "dorm_name": dorm.name,
                                "group": rec.group
                            })
                        global_group_counter += 1

                    # Распределяем оставшиеся записи по полу (если есть)
                    if male_records:
                        group_label = str(global_group_counter)
                        global_group_counter += 1
                        for rec in male_records:
                            rec.dorm_id = dorm
                            rec.group = group_label
                            rec.save()
                            allocated_students.append({
                                "student_email": rec.student_id.email,
                                "dorm_name": dorm.name,
                                "group": group_label
                            })
                    if female_records:
                        group_label = str(global_group_counter)
                        global_group_counter += 1
                        for rec in female_records:
                            rec.dorm_id = dorm
                            rec.group = group_label
                            rec.save()
                            allocated_students.append({
                                "student_email": rec.student_id.email,
                                "dorm_name": dorm.name,
                                "group": group_label
                            })

        return Response(
            {
                "detail": "Студенты успешно распределены по общежитиям и группам.",
                "allocated_students": allocated_students
            },
            status=status.HTTP_200_OK
        )

    def allocate_slot(self, candidate_pool, slot_size):
        """
        Функция пытается выделить слот (комнату) требуемого размера из списка записей StudentInDorm.
        Сначала группирует записи по результату теста (поле test_result заявки)
        и, желательно, по языковому предпочтению (из test_answers, где 'A' – казахский, 'B' – русский).
        Если записей меньше, чем slot_size, возвращает None.
        """
        if len(candidate_pool) < slot_size:
            return None

        groups = defaultdict(list)
        for record in candidate_pool:
            groups[record.application_id.test_result].append(record)

        for test_result, recs in groups.items():
            if len(recs) >= slot_size:
                lang_groups = defaultdict(list)
                for record in recs:
                    lang = self.get_language_from_record(record)
                    lang_groups[lang].append(record)
                for lang in ['A', 'B']:
                    if lang_groups.get(lang, []) and len(lang_groups[lang]) >= slot_size:
                        return lang_groups[lang][:slot_size]
                return recs[:slot_size]

        sorted_groups = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)
        largest_group_recs = sorted_groups[0][1]
        allocated = largest_group_recs[:]
        remaining_needed = slot_size - len(allocated)
        remaining = [record for record in candidate_pool if record not in allocated]
        if len(remaining) < remaining_needed:
            return None
        allocated.extend(remaining[:remaining_needed])
        if len(allocated) == slot_size:
            return allocated
        return None

    def get_language_from_record(self, record):
        """
        Извлекает языковое предпочтение из поля test_answers заявки.
        Предполагается, что test_answers хранит JSON-массив, где первый элемент – ответ ('A' – казахский, 'B' – русский, 'C' – оба).
        """
        try:
            answers = record.application_id.test_answers
            if isinstance(answers, str):
                answers = json.loads(answers)
            if isinstance(answers, list) and len(answers) > 0:
                return answers[0]
        except Exception as e:
            return None



class IssueOrderAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        # Выбираем все записи в StudentInDorm, у которых связанная заявка имеет статус "awaiting_order"
        waiting_records = StudentInDorm.objects.filter(application_id__status='awaiting_order')
        processed_students = []
        for record in waiting_records:
            # Обновляем статус заявки, связанной с данной записью
            application = record.application_id
            application.status = 'order'
            application.save()

            student = record.student_id  # объект модели Student
            dorm = record.dorm_id        # объект модели Dorm (возможно, может быть None, если общага не назначена)
            room = record.room

            dorm_name = dorm.name if dorm is not None else "Не назначена"

            try:
                send_mail(
                    subject="Ордер на заселение в общежитие",
                    message=(
                        f"Поздравляем, вам выдан ордер на заселение в общежитие!\n"
                        f"Общежитие: {dorm_name}\n"
                        f"Комната: {room}"
                    ),
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[student.email],
                    fail_silently=False,
                )
            except Exception as e:
                print(f"Ошибка отправки письма на {student.email}: {e}")

            processed_students.append({
                "student_email": student.email,
                "dorm_name": dorm_name,
                "room": room
            })

        return Response(
            {
                "detail": "Статусы обновлены и письма отправлены.",
                "processed_students": processed_students
            },
            status=status.HTTP_200_OK
        )



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


class DormImageViewSet(viewsets.ModelViewSet):
    queryset = DormImage.objects.all()
    serializer_class = DormImageSerializer
    # permission_classes = [IsAdmin]

    def perform_create(self, serializer):
        dorm_id = self.request.data.get("dorm")
        if dorm_id:
            try:
                dorm_obj = Dorm.objects.get(id=dorm_id)
            except Dorm.DoesNotExist:
                raise ValidationError(f"Общага с id {dorm_id} не существует.")
            serializer.save(dorm=dorm_obj)
        else:
            raise ValidationError("Поле 'dorm' обязательно для заполнения.")


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





class AssignRoomAPIView(APIView):
    permission_classes = [IsAdmin]  # или ваш кастомный IsAdmin

    def post(self, request, *args, **kwargs):
        """
        Ожидается, что фронтенд отправит JSON-объект вида:
        {
            "student_ids": [1, 3, 5],
            "room": "101A"
        }
        Вьюшка обновит поле room для записей StudentInDorm с указанными id.
        """
        student_ids = request.data.get("student_ids")
        room_number = request.data.get("room")

        if not student_ids or not isinstance(student_ids, list):
            return Response(
                {"detail": "Необходимо передать список идентификаторов студентов."},
                status=status.HTTP_400_BAD_REQUEST
            )
        if not room_number:
            return Response(
                {"detail": "Необходимо указать номер комнаты."},
                status=status.HTTP_400_BAD_REQUEST
            )

        with transaction.atomic():
            qs = StudentInDorm.objects.filter(id__in=student_ids)
            if not qs.exists():
                return Response(
                    {"detail": "Записи по переданным id не найдены."},
                    status=status.HTTP_404_NOT_FOUND
                )
            updated_count = qs.update(room=room_number)

        return Response(
            {"detail": f"Номер комнаты '{room_number}' назначен для {updated_count} студентов."},
            status=status.HTTP_200_OK
        )


class StudentApplicationUpdateView(APIView):
    """
    Вьюшка для обновления заявки студентом.
    Студент может менять только dormitory_cost и добавлять/удалять свои справки.
    ID заявки берется из авторизованного пользователя (через request.user.application).

    Ожидаемый формат запроса (JSON или multipart, если передаются файлы):
    {
       "dormitory_cost": 1234,  # Опционально – новая цена проживания
       "add_evidences": [
            {
                "evidence_type": <evidence_type_id>,
                # если файл передается, его обработку нужно реализовать через multipart,
                # либо передавать URL/данные файла – здесь пример без файла:
                "numeric_value": 95.5
            },
            ... // можно добавить несколько справок
       ],
       "delete_evidences": [3, 5]  # Список id справок, которые нужно удалить
    }
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        """Получение данных заявки студента."""
        try:
            application = request.user.application
        except Application.DoesNotExist:
            return Response({"detail": "Заявка не найдена."}, status=status.HTTP_404_NOT_FOUND)
        serializer = ApplicationSerializer(application, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):

        try:
            application = request.user.application
        except Application.DoesNotExist:
            return Response({"detail": "Заявка не найдена."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data

        new_cost = data.get("dormitory_cost", None)
        if new_cost is not None:
            application.dormitory_cost = new_cost
            application.save()

        added_evidences = []
        add_list = data.get("add_evidences", [])
        for evidence_data in add_list:
            evidence_data["application"] = application.id
            serializer = ApplicationEvidenceSerializer(data=evidence_data, context={'request': request})
            if serializer.is_valid():
                serializer.save()
                added_evidences.append(serializer.data)
            else:
                return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        deleted_ids = []
        delete_list = data.get("delete_evidences", [])
        for evidence_id in delete_list:
            try:
                evidence = ApplicationEvidence.objects.get(id=evidence_id, application=application)
                evidence.delete()
                deleted_ids.append(evidence_id)
            except ApplicationEvidence.DoesNotExist:
                pass

        application.refresh_from_db()
        serializer = ApplicationSerializer(application, context={'request': request})
        return Response({
            "application": serializer.data,
            "added_evidences": added_evidences,
            "deleted_evidences": deleted_ids,
        }, status=status.HTTP_200_OK)
