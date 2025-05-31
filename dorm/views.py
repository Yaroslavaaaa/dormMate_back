from django.core.exceptions import ObjectDoesNotExist
from rest_framework import status, generics
from rest_framework.pagination import PageNumberPagination
from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import *
from rest_framework.generics import RetrieveUpdateAPIView
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import NotFound
from django.http import Http404, JsonResponse
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.views.generic import View
from rest_framework.generics import ListAPIView
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.generics import RetrieveAPIView
from django.db.models import Q
from .utils import *
from rest_framework import viewsets, permissions
import requests


class RegionListView(generics.ListAPIView):
    queryset = Region.objects.all()
    serializer_class = RegionSerializer


class StudentInDormView(generics.ListAPIView):
    queryset = StudentInDorm.objects.all()
    serializer_class = StudentInDormSerializer


class TestQuestionViewSet(generics.ListAPIView):
    queryset = TestQuestion.objects.all()
    serializer_class = TestQuestionSerializer


class IsAdmin(IsAuthenticated):
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        return is_authenticated and (hasattr(request.user, 'admin') or request.user.is_superuser)


class IsAuthenticatedAdmin(permissions.IsAuthenticated):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False
        return hasattr(request.user, 'admin') or request.user.is_superuser


class IsSuperAdmin(IsAuthenticatedAdmin):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        if request.user.is_superuser:
            return True

        return (
                hasattr(request.user, 'admin')
                and request.user.admin.role == Admin.ROLE_SUPER
        )


class IsOperator(IsAuthenticatedAdmin):
    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        if hasattr(request.user, 'admin') and request.user.admin.role == Admin.ROLE_SUPER:
            return True

        return (
                hasattr(request.user, 'admin')
                and request.user.admin.role == Admin.ROLE_OPERATOR
        )


class IsRequestAdmin(IsAuthenticatedAdmin):

    def has_permission(self, request, view):
        if not super().has_permission(request, view):
            return False

        if hasattr(request.user, 'admin') and request.user.admin.role in {
            Admin.ROLE_SUPER, Admin.ROLE_OPERATOR
        }:
            return True

        return (
                hasattr(request.user, 'admin')
                and request.user.admin.role == Admin.ROLE_REQUEST
        )


class KnowledgeBaseListView(generics.ListAPIView):
    queryset = KnowledgeBase.objects.all()
    serializer_class = KnowledgeBaseSerializer
    permission_classes = [permissions.IsAdminUser]


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


class PDFView(View):
    def get(self, request, pk, evidence_code):
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


class IsStudent(IsAuthenticated):
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        return is_authenticated and hasattr(request.user, 'student')


class KeywordViewSet(viewsets.ModelViewSet):
    queryset = Keyword.objects.all()
    serializer_class = KeywordSerializer
    permission_classes = [IsAdmin]


class EvidenceTypeViewSet(viewsets.ModelViewSet):
    queryset = EvidenceType.objects.all().order_by('-priority')
    serializer_class = EvidenceTypeSerializer

    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return []
        return [IsAdmin()]


class DormCostListView(APIView):
    def get(self, request):
        costs = Dorm.objects.values_list('cost', flat=True).distinct()
        return Response(sorted(costs), status=status.HTTP_200_OK)


class CustomTokenObtainView(APIView):
    def post(self, request, *args, **kwargs):
        serializer = CustomTokenObtainSerializer(data=request.data)
        if serializer.is_valid():
            return Response(serializer.validated_data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


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
            return Response({"message": "Вопрос отправлен администратору"},
                            status=status.HTTP_201_CREATED)


class CreateChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        student = request.user
        active_chat = Chat.objects.filter(student=student, is_active=True).first()
        if active_chat:
            return Response({"id": active_chat.id}, status=status.HTTP_200_OK)

        new_chat = Chat.objects.create(student=student)
        return Response({"id": new_chat.id}, status=status.HTTP_201_CREATED)


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
        query = request.query_params.get('query', '').strip()

        chats = Chat.objects.filter(is_active=True)

        if query:
            parts = query.split()
            query_upper = query.upper()

            s_filter = Q(student__s__icontains=query_upper)

            if len(parts) == 1:
                p = parts[0]
                fio_filter = (
                        Q(student__first_name__icontains=p) |
                        Q(student__last_name__icontains=p) |
                        Q(student__middle_name__icontains=p)
                )
            else:
                fio_filter = Q()
                for p in parts:
                    fio_filter &= (
                            Q(student__first_name__icontains=p) |
                            Q(student__last_name__icontains=p) |
                            Q(student__middle_name__icontains=p)
                    )

            chats = chats.filter(s_filter | fio_filter)

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

        # Сохраняем сообщение от пользователя
        Message.objects.create(chat=chat, sender=sender, receiver=receiver, content=text)

        # Если пишет студент — обрабатываем ИИ
        if not sender.is_staff:
            # Если оператор уже подключён — бот не отвечает
            if chat.is_operator_connected:
                return Response({"status": "Сообщение отправлено"}, status=status.HTTP_201_CREATED)

            # 🔗 Обращение к ИИ
            try:
                ai_response = requests.post(
                    "https://a7ssmm.pythonanywhere.com/chat",
                    json={"question": text},
                    timeout=20
                )

                if ai_response.status_code == 200 and ai_response.json().get("answer"):
                    ai_answer = ai_response.json()["answer"].strip()
                    confidence = ai_response.json().get("confidence", 0.0)

                    if ai_answer and len(ai_answer) > 5:
                        bot_user, _ = User.objects.get_or_create(
                            s="F22016183",
                            defaults={
                                "first_name": "DormMateBot",
                                "is_staff": True,
                                "is_active": True,
                                "phone_number": "00000000001",
                                "password": "pbkdf2_sha256$260000$fakebotpassword$fakehashedpassword"
                            }
                        )

                        Message.objects.create(
                            chat=chat,
                            sender=bot_user,
                            receiver=sender,
                            content=ai_answer,
                            is_from_bot=True
                        )

                        return Response({"status": "Ответ сгенерирован ботом"}, status=status.HTTP_201_CREATED)

            except Exception as e:
                print("Ошибка запроса к ИИ:", e)

            # Если бот не справился → уведомляем оператора
            admin = User.objects.filter(is_staff=True).first()

            if admin:
                Notification.objects.create(
                    recipient=admin,
                    message=f"Новый вопрос в чате #{chat.id}, требуется участие оператора."
                )

                Message.objects.create(
                    chat=chat,
                    sender=admin,
                    receiver=sender,
                    content="Здравствуйте! Я подключаюсь к вам как оператор. Чем могу помочь?",
                    is_from_bot=True
                )

            return Response({"status": "Оператор уведомлён, бот не смог ответить"}, status=status.HTTP_200_OK)

        return Response({"status": "Сообщение отправлено"}, status=status.HTTP_201_CREATED)



class EndChatView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request, chat_id):
        chat = get_object_or_404(Chat, id=chat_id, is_active=True)
        if request.user.is_staff or chat.student == request.user:
            chat.is_active = False
            chat.status = 'closed'
            chat.is_operator_connected = False
            chat.save()
            return Response({"status": "Чат завершён"}, status=status.HTTP_200_OK)
        return Response({"error": "Нет доступа к этому чату."}, status=status.HTTP_403_FORBIDDEN)


class ChatDetailView(RetrieveAPIView):
    queryset = Chat.objects.all()
    serializer_class = ChatSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = 'id'


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
            return Response({"error": "New password and confirm password do not match."},
                            status=status.HTTP_400_BAD_REQUEST)

        if len(new_password) < 8:
            return Response({"error": "The new password must be at least 8 characters long."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[A-Za-z]', new_password):
            return Response({"error": "The new password must contain at least one letter."},
                            status=status.HTTP_400_BAD_REQUEST)
        if not re.search(r'[\W_]', new_password):
            return Response({"error": "The new password must contain at least one special character."},
                            status=status.HTTP_400_BAD_REQUEST)

        if not user.check_password(old_password):
            return Response({"error": "Current password is incorrect."}, status=status.HTTP_400_BAD_REQUEST)

        user.set_password(new_password)
        user.save()

        return Response({"message": "Password successfully updated."}, status=status.HTTP_200_OK)


class IsAdminOrOwnerAndEditable(permissions.BasePermission):

    def has_object_permission(self, request, view, obj):
        if request.user.is_staff:
            return True

        if request.method in permissions.SAFE_METHODS:
            return hasattr(request.user, 'student') and obj.student == request.user.student

        settings = GlobalSettings.get_solo()
        is_owner = hasattr(request.user, 'student') and obj.student == request.user.student
        return settings.allow_application_edit and is_owner


class ApplicationPagination(PageNumberPagination):
    page_size = 2
    page_size_query_param = 'page_size'
    # max_page_size = 100


class ApplicationViewSet(viewsets.ModelViewSet):
    queryset = Application.objects.all()
    serializer_class = ApplicationSerializer
    permission_classes = [IsAuthenticated, IsAdminOrOwnerAndEditable]
    pagination_class = ApplicationPagination

    def get_queryset(self):
        user = self.request.user
        if user.is_staff:
            return Application.objects.all()
        return Application.objects.filter(student=user.student)

    def get_paginated_response(self, data):
        paginator = self.paginator
        return Response({
            'count': paginator.page.paginator.count,
            'next': paginator.get_next_link(),
            'previous': paginator.get_previous_link(),
            'results': data,
            'page_size': self.pagination_class.page_size
        })


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


class GlobalSettingsAPIView(APIView):
    def get_permissions(self):
        if self.request.method in ['GET', 'HEAD', 'OPTIONS']:
            return []
        return [IsAdmin()]

    def get(self, request):
        settings = GlobalSettings.get_solo()
        return Response(GlobalSettingsSerializer(settings).data)

    def post(self, request):
        settings = GlobalSettings.get_solo()
        serializer = GlobalSettingsSerializer(settings, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()
        return Response(serializer.data)


class StudentsViewSet(viewsets.ModelViewSet):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer

    def get_queryset(self):
        qs = super().get_queryset()
        query = self.request.query_params.get('query', '').strip()
        if query:
            parts = query.split()
            s_filter = Q(s__icontains=query.upper())
            fio_filter = Q()
            for part in parts:
                fio_filter &= (
                        Q(first_name__icontains=part) |
                        Q(last_name__icontains=part) |
                        Q(middle_name__icontains=part)
                )
            qs = qs.filter(s_filter | fio_filter)
        return qs

    def perform_create(self, serializer):
        s_value = serializer.validated_data.get('s')
        if Student.objects.filter(s=s_value).exists():
            raise ValidationError(f"Student with s = {s_value} already exists.")
        serializer.save()


class UserApplicationView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        try:
            application = Application.objects.get(student=request.user)
            serializer = ApplicationSerializer(application)
            return Response(serializer.data)
        except Application.DoesNotExist:
            return Response({'detail': 'Заявка не найдена.'}, status=404)


class AdminViewSet(viewsets.ModelViewSet):
    queryset = Admin.objects.all()
    serializer_class = AdminSerializer
    permission_classes = [IsAdmin]


class ApplicationListView(ListAPIView):
    serializer_class = ApplicationSerializer

    def get_queryset(self):
        queryset = Application.objects.select_related('student')

        return queryset


class ApplicationEvidenceListView(APIView):
    permission_classes = [IsAuthenticated, IsStudent]

    def get(self, request, *args, **kwargs):
        qs = ApplicationEvidence.objects.filter(
            application__student=request.user.student
        ).order_by('created_at')

        serializer = ApplicationEvidenceSerializer(
            qs, many=True, context={'request': request}
        )
        return Response(serializer.data)
