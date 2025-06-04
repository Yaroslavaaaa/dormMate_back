from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from rest_framework import status, generics
from rest_framework.views import APIView
from rest_framework.response import Response
from .serializers import *
from collections import Counter
from django.shortcuts import get_object_or_404
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import IsAuthenticated
from django.db import transaction
from rest_framework.parsers import MultiPartParser, FormParser
import PyPDF2
from rest_framework import permissions
from django.core.files.storage import default_storage


class IsStudent(IsAuthenticated):
    def has_permission(self, request, view):
        is_authenticated = super().has_permission(request, view)
        return is_authenticated and hasattr(request.user, 'student')


def extract_text_from_pdf(file_obj):
    text = ""
    try:
        reader = PyPDF2.PdfReader(file_obj)
        for page in reader.pages:
            page_text = page.extract_text() or ""
            text += page_text
    except Exception as e:
        text = ""
    return text


def extract_ent_score_from_pdf(file_obj):
    """
    Читает весь текст из PDF (file_obj) и ищет шаблон вида:
        <число> Барлығы/Итого
    Возвращает найденное число (int) или выдаёт ValidationError, если не найдено.
    """
    try:
        reader = PyPDF2.PdfReader(file_obj)
    except Exception as e:
        raise ValidationError(f"Ошибка при чтении PDF: {str(e)}")

    full_text = ""
    for page in reader.pages:
        try:
            full_text += page.extract_text() or ""
        except Exception:
            continue

    # Иногда в PDF может быть перенос строки между числом и текстом, приведём всё к одной строке
    normalized = full_text.replace('\n', ' ')
    # Ищем число перед словом "Барлығы" (каз.) или "Итого" (рус.), без учёта регистра
    pattern = r"(\d+)\s*(?:Барлығы|Итого)"
    match = re.search(pattern, normalized, flags=re.IGNORECASE)
    if not match:
        raise ValidationError("Не удалось найти итоговый балл ЕНТ (Барлығы/Итого) в PDF.")
    return int(match.group(1))


class CreateApplicationView(APIView):
    permission_classes = [IsStudent]
    parser_classes = (MultiPartParser, FormParser)

    def post(self, request):
        student_id = request.user.student.id
        dormitory_cost = request.data.get('dormitory_cost')

        if not student_id:
            return Response({"error": "Поле 'student' обязательно"}, status=status.HTTP_400_BAD_REQUEST)

        if not dormitory_cost:
            return Response({"error": "Поле 'dormitory_cost' обязательно"}, status=status.HTTP_400_BAD_REQUEST)

        if not Dorm.objects.filter(cost=dormitory_cost).exists():
            return Response({"error": "Общежитий с выбранной стоимостью не найдено"},
                            status=status.HTTP_400_BAD_REQUEST)

        try:
            student = Student.objects.get(pk=student_id)
        except Student.DoesNotExist:
            return Response({"error": "Студент с таким ID не найден"}, status=status.HTTP_400_BAD_REQUEST)

        serializer = ApplicationSerializer(data=request.data)
        if serializer.is_valid():
            try:
                with transaction.atomic():
                    # 1) Сохраняем саму заявку (пока без ent_result)
                    application = serializer.save(student=student, dormitory_cost=dormitory_cost)

                    # 2) Проходим по всем загруженным файлам (request.FILES)
                    #    Предполагается, что поле "ключ" – это код типа документа (EvidenceType.code)
                    #    Если код соответствует сертификату ЕНТ, парсим оттуда балл.
                    for key, file in request.FILES.items():
                        try:
                            evidence_type = EvidenceType.objects.get(code=key)
                        except EvidenceType.DoesNotExist:
                            # Если для данного кода нет типа доказательства — пропускаем
                            continue

                        if file.content_type != 'application/pdf':
                            raise ValidationError(f"Файл в поле '{key}' должен быть формата PDF.")

                        # Если этот тип доказательства — сертификат ЕНТ (код, например, 'ent_certificate'),
                        # то сразу извлекаем из него число и сохраняем в application.ent_result
                        if evidence_type.code == 'ent_certificate':
                            # Обратите внимание: file — это InMemoryUploadedFile, поэтому перед чтением seek(0)
                            file.seek(0)
                            ent_score = extract_ent_score_from_pdf(file)
                            # Сохраняем найденный балл в заявку и сбрасываем указатель
                            application.ent_result = ent_score
                            application.save()
                            # Чтобы при повторном чтении PDF PyPDF2 не "потерял" поток, делаем seek(0) снова
                            file.seek(0)

                        # 3) Проверяем ключевые слова (если у EvidenceType указаны keywords)
                        extracted_text = ''
                        try:
                            file.seek(0)
                            reader = PyPDF2.PdfReader(file)
                            for page in reader.pages:
                                extracted_text += page.extract_text() or ""
                        except Exception:
                            # Если не удалось извлечь текст — будем дальше только сохранять файл
                            extracted_text = ''

                        keywords = evidence_type.keywords.all()
                        if keywords and not any(
                                keyword.keyword.lower() in extracted_text.lower()
                                for keyword in keywords
                        ):
                            raise ValidationError(
                                f"Загруженный файл для '{evidence_type.name}' не содержит необходимых ключевых слов."
                            )

                        # 4) Если всё ок, создаём запись ApplicationEvidence
                        ApplicationEvidence.objects.create(
                            application=application,
                            evidence_type=evidence_type,
                            file=file
                        )

                    # 5) Автозаполнение по data_type у остальных типов evidence
                    evidence_types_with_auto_fill = EvidenceType.objects.exclude(
                        auto_fill_field__isnull=True
                    ).exclude(auto_fill_field='')

                    for evidence_type in evidence_types_with_auto_fill:
                        auto_field = evidence_type.auto_fill_field
                        student_value = getattr(student, auto_field, None)

                        if student_value is not None:
                            if evidence_type.data_type == 'numeric':
                                ApplicationEvidence.objects.create(
                                    application=application,
                                    evidence_type=evidence_type,
                                    numeric_value=student_value
                                )
                            elif evidence_type.data_type == 'file':
                                # Если auto_fill_field указывает на поле-файл в модели Student,
                                # можно скопировать его внутрь ApplicationEvidence.file
                                source_file = getattr(student, auto_field)
                                if source_file:
                                    ApplicationEvidence.objects.create(
                                        application=application,
                                        evidence_type=evidence_type,
                                        file=source_file
                                    )

                return Response(
                    {
                        "message": "Заявка успешно создана",
                        "application_id": application.id,
                        # Дополнительно можем вернуть ent_result, если он был заполнен
                        "ent_result": application.ent_result
                    },
                    status=status.HTTP_201_CREATED
                )

            except ValidationError as e:
                # Откат транзакции при любой ошибке валидации
                return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

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
                             "payment_url": "http://127.0.0.1:8000/api/v1/upload_payment_screenshot/"},
                            status=status.HTTP_200_OK)

        if application.status == 'rejected':
            return Response({"status": "Ваша заявка была отклонена."}, status=status.HTTP_200_OK)

        if application.status == 'awaiting_payment':
            return Response({
                "status": "Ваша заявка одобрена, внесите оплату и прикрепите сюда чек.",
                "payment_url": "http://127.0.0.1:8000/api/v1/upload_payment_screenshot/"
            }, status=status.HTTP_200_OK)

        if application.status == 'awaiting_order':
            return Response({"status": "Ваша заявка принята, ожидайте ордер на заселение."}, status=status.HTTP_200_OK)

        student_in_dorm = StudentInDorm.objects.filter(application_id=application.id).first()
        dormitory_name = student_in_dorm.dorm_id
        room = student_in_dorm.room

        if application.status == 'order':
            return Response({"status": f"Поздравляем! Вам выдан ордер в общежитие: {dormitory_name}, комната {room}"},
                            status=status.HTTP_200_OK)

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

        return Response({"message": "Скрин оплаты успешно прикреплен, заявка принята. Ожидайте ордер."},
                        status=status.HTTP_200_OK)


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

        return Response({"message": "Ваша заявка принята", "result_letter": most_common_letter},
                        status=status.HTTP_200_OK)


class StudentChatListView(generics.ListAPIView):
    serializer_class = ChatSerializer
    permission_classes = [IsStudent]

    def get_queryset(self):
        return Chat.objects.filter(student=self.request.user, is_active=True)


class RequestAdminView(APIView):
    permission_classes = [IsStudent]

    def post(self, request):
        chat_id = request.data.get('chat_id')
        chat = get_object_or_404(Chat, id=chat_id, is_active=True, student=request.user)

        admins = User.objects.filter(is_staff=True)

        if not admins.exists():
            return Response({"error": "Нет доступных админов"}, status=status.HTTP_404_NOT_FOUND)

        chat.is_operator_connected = True
        chat.save()

        Message.objects.create(
            chat=chat,
            sender=request.user,
            receiver=None,
            content="Здравствуйте! Мне требуется помощь оператора.",
            is_from_bot=False
        )

        student_name = (request.user.username if hasattr(request.user, 'username') else request.user.s)[:50]
        message = f"Студент {student_name} просит подключить оператора к чату #{chat.id}"

        for admin in admins:
            Notification.objects.create(
                recipient=admin,
                message=message
            )

        channel_layer = get_channel_layer()
        async_to_sync(channel_layer.group_send)(
            "admin_notifications",
            {
                "type": "new_chat",
                "chat_id": chat.id,
                "student": student_name,
                "question": "Запрос оператора"
            }
        )

        return Response({"status": "Операторы уведомлены"}, status=status.HTTP_200_OK)


class AvatarUploadView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        student = request.user.student
        avatar = request.FILES.get('avatar')

        if not avatar:
            return Response({'error': 'Файл не выбран'}, status=status.HTTP_400_BAD_REQUEST)

        student.avatar = avatar
        student.save()

        return Response({'message': 'Аватар успешно обновлен.', 'avatar_url': student.avatar.url},
                        status=status.HTTP_200_OK)

    def delete(self, request):
        student = request.user.student
        if student.avatar:
            if default_storage.exists(student.avatar.name):
                default_storage.delete(student.avatar.name)

            student.avatar.delete(save=False)
            student.avatar = None
            student.save()

            return Response({'message': 'Аватар удалён.'}, status=status.HTTP_200_OK)
        else:
            return Response({'error': 'Аватар не установлен.'}, status=status.HTTP_400_BAD_REQUEST)



class StudentApplicationUpdateView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get(self, request, *args, **kwargs):
        try:
            application = request.user.student.application
        except (Student.DoesNotExist, Application.DoesNotExist):
            return Response({"detail": "Заявка не найдена."}, status=status.HTTP_404_NOT_FOUND)

        serializer = ApplicationSerializer(application, context={'request': request})
        return Response(serializer.data)

    def patch(self, request, *args, **kwargs):
        try:
            application = request.user.student.application
        except (Student.DoesNotExist, Application.DoesNotExist):
            return Response({"detail": "Заявка не найдена."}, status=status.HTTP_404_NOT_FOUND)

        data = request.data

        changed = False
        for field in ("dormitory_cost", "parent_phone", "ent_result"):
            if field in data:
                setattr(application, field, data[field])
                changed = True
        if changed:
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
