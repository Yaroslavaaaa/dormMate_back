from asgiref.sync import async_to_sync
from channels.layers import get_channel_layer
from django.core.exceptions import ObjectDoesNotExist
from rest_framework import viewsets, status, generics, filters, permissions, request
from rest_framework.pagination import PageNumberPagination
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
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.generics import RetrieveAPIView


from rest_framework.permissions import BasePermission
import PyPDF2

from .utils import *




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




class MyAdminRoleAPIView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user

        if user.is_superuser:
            role_code = Admin.ROLE_SUPER
            role_label = dict(Admin.ROLE_CHOICES)[role_code]
            return Response({'role': role_code, 'label': role_label})

        try:
            admin_obj = user.admin
        except Admin.DoesNotExist:
            return Response(
                {'detail': 'У вас нет прав администратора.'},
                status=status.HTTP_403_FORBIDDEN
            )

        role_code = admin_obj.role

        if role_code == Admin.ROLE_SUPER:
            role_label = dict(Admin.ROLE_CHOICES)[Admin.ROLE_SUPER]
            return Response({'role': Admin.ROLE_SUPER, 'label': role_label})

        role_label = dict(Admin.ROLE_CHOICES).get(role_code, 'Неизвестная роль')
        return Response({'role': role_code, 'label': role_label})






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
                        'iin': row['iin'],
                        'is_active': True,
                    }
                )

                if created:
                    student.set_password(password)
                    student.save()

            return Response({"status": "success", "data": "Данные успешно загружены и обновлены"},
                            status=status.HTTP_201_CREATED)

        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)





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

        sorted_applications = sorted(
            pending_applications,
            key=lambda app: calculate_application_score(app),
            reverse=True
        )

        selected_applications = sorted_applications[:total_places]
        rejected_applications = sorted_applications[total_places:]

        approved_students = []

        with transaction.atomic():
            for application in selected_applications:
                application.approval = True
                application.status = "approved"
                application.save()
                approved_students.append({
                    "student_s": getattr(application.student, "s", "Нет S"),
                    "first_name": getattr(application.student, 'first_name', 'Нет имени'),
                    "last_name": getattr(application.student, 'last_name', 'Нет имени'),
                    "course": getattr(application.student, 'course', 'Не указан'),
                    "ent_result": application.ent_result,
                })

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
        excel_file = request.FILES.get('excel_file')
        if not excel_file:
            return Response(
                {"detail": "Excel-файл обязателен для проверки данных студентов."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            return Response(
                {"detail": f"Ошибка при чтении Excel-файла: {str(e)}"},
                status=status.HTTP_400_BAD_REQUEST
            )


        valid_payments = {}
        for _, row in df.iterrows():
            raw_iin = row.get('iin') or row.get('ИИН')
            if pd.isna(raw_iin):
                continue
            iin = str(raw_iin).strip()

            paid = row.get('Оплачено')
            if pd.isna(paid):
                continue
            paid_amount = float(paid)

            valid_payments[iin] = paid_amount

        approved_apps = Application.objects.filter(
            approval=True,
            payment_screenshot__isnull=False
        ).exclude(payment_screenshot="")

        added_students = []
        with transaction.atomic():
            for app in approved_apps:
                student = app.student
                student_iin = str(student.iin).strip() if student.iin else None

                if not student_iin or student_iin not in valid_payments:
                    continue

                excel_paid = valid_payments[student_iin]

                if excel_paid == app.dormitory_cost:
                    app.is_full_payment = True
                elif excel_paid == (app.dormitory_cost / 2):
                    app.is_full_payment = False
                else:
                    app.is_full_payment = None

                app.status = 'awaiting_order'
                app.save()

                if app.is_full_payment is not None:
                    created = StudentInDorm.objects.filter(
                        student_id=student,
                        application_id=app
                    ).exists()
                    if not created:
                        StudentInDorm.objects.create(
                            student_id=student,
                            dorm_id=None,
                            group=None,
                            application_id=app,
                        )
                        added_students.append({
                            "student_iin": student_iin,
                            "application_id": app.id,
                            "paid": excel_paid
                        })

        return Response(
            {
                "detail": "Оплата подтверждена на основании колонки «Оплачено».",
                "added_students": added_students
            },
            status=status.HTTP_200_OK
        )




class DistributeStudentsAPIView2(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        # 1. Берём только те записи StudentInDorm,
        #    где связанная заявка в status='waiting_order' и dorm ещё не назначен
        pending_records = StudentInDorm.objects.filter(
            application_id__status='waiting_order',
            dorm_id__isnull=True
        )
        if not pending_records.exists():
            return Response(
                {"detail": "Нет студентов, ожидающих распределения по общежитиям."},
                status=200
            )

        # 2. Группируем записи по стоимости (dormitory_cost берётся из Application)
        cost_to_records = defaultdict(list)
        for rec in pending_records:
            cost = rec.application_id.dormitory_cost
            cost_to_records[cost].append(rec)

        allocated_students = []
        group_counter = 1

        with transaction.atomic():
            for cost, records in cost_to_records.items():
                # выбираем все общежития с этой стоимостью
                dorms_for_cost = Dorm.objects.filter(cost=cost)
                if not dorms_for_cost:
                    continue

                for dorm in dorms_for_cost:
                    # собираем список доступных слотов по комнатам
                    slots = []
                    slots += [2] * (dorm.rooms_for_two or 0)
                    slots += [3] * (dorm.rooms_for_three or 0)
                    slots += [4] * (dorm.rooms_for_four or 0)
                    if not slots:
                        continue

                    # оставшиеся неподразмещённые записи
                    remaining = [r for r in records if r.dorm_id is None]
                    if not remaining:
                        continue

                    # разделяем по полу
                    male = [r for r in remaining if r.student_id.gender and r.student_id.gender.upper() == 'M']
                    female = [r for r in remaining if r.student_id.gender and r.student_id.gender.upper() == 'F']

                    # пытаемся заполнить каждый слот
                    for size in sorted(slots):
                        pool, gender = None, None
                        if len(male) >= size and len(female) >= size:
                            pool, gender = (male, 'M') if len(male) >= len(female) else (female, 'F')
                        elif len(male) >= size:
                            pool, gender = male, 'M'
                        elif len(female) >= size:
                            pool, gender = female, 'F'
                        else:
                            continue

                        group = self.allocate_slot(pool, size)
                        if not group:
                            continue

                        for rec in group:
                            # убираем из пулов выбранных
                            if gender == 'M':
                                male.remove(rec)
                            else:
                                female.remove(rec)

                            rec.dorm_id = dorm
                            rec.group = str(group_counter)
                            rec.save()

                            allocated_students.append({
                                "student_email": rec.student_id.email,
                                "dorm_name": dorm.name,
                                "group": rec.group
                            })
                        group_counter += 1

                    # если после основных слотов остались студенты, распределяем их по тем же принципам
                    for pool in (male, female):
                        if not pool:
                            continue
                        label = str(group_counter)
                        for rec in pool:
                            rec.dorm_id = dorm
                            rec.group = label
                            rec.save()
                            allocated_students.append({
                                "student_email": rec.student_id.email,
                                "dorm_name": dorm.name,
                                "group": rec.group
                            })
                        group_counter += 1

        return Response({
            "detail": "Студенты успешно распределены по общежитиям и группам.",
            "allocated_students": allocated_students
        }, status=200)

    def allocate_slot(self, candidate_pool, slot_size):
        """
        Пытаемся собрать группу заданного размера:
        1) Сначала по test_result
        2) Внутри — по языковому ответу (test_answers)
        3) Если не получается — берём из самой большой группы и дополняем другими
        """
        if len(candidate_pool) < slot_size:
            return None

        # Группируем по результату теста
        groups = defaultdict(list)
        for rec in candidate_pool:
            tr = rec.application_id.test_result
            groups[tr].append(rec)

        # Ищём внутри каждой группы подходящую по языку
        for tr, recs in groups.items():
            if len(recs) >= slot_size:
                # группируем по языковому ответу
                langs = defaultdict(list)
                for r in recs:
                    ans = r.application_id.test_answers
                    lang = self.get_language_from_record(ans)
                    langs[lang].append(r)
                # пытаемся по конкретному языку
                for lang in ('A', 'B'):
                    if len(langs.get(lang, [])) >= slot_size:
                        return langs[lang][:slot_size]
                # иначе просто возвращаем первые slot_size из этой группы
                return recs[:slot_size]

        # Если ни по одной группе по test_result не сработало,
        # берём из самой крупной группы и докидываем остальных
        sorted_groups = sorted(groups.items(), key=lambda x: len(x[1]), reverse=True)
        top_recs = sorted_groups[0][1]
        allocated = top_recs[:]
        remaining_needed = slot_size - len(allocated)
        rest = [r for r in candidate_pool if r not in allocated]
        if len(rest) < remaining_needed:
            return None
        allocated.extend(rest[:remaining_needed])
        return allocated if len(allocated) == slot_size else None

    def get_language_from_record(self, test_answers):
        """
        Извлекает первый ответ из test_answers:
        - если строка — парсим JSON
        - если список — берём первый элемент
        """
        try:
            answers = test_answers
            if isinstance(answers, str):
                answers = json.loads(answers)
            if isinstance(answers, list) and answers:
                return answers[0]
        except Exception:
            pass
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

        partial_applications = Application.objects.filter(
            approval=True,
            payment_screenshot__isnull=False
        ).exclude(payment_screenshot="").filter(
            is_full_payment=False
        )

        reminded_emails = []

        for app in partial_applications:
            student_email = app.student.email
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




class ExportStudentInDormExcelView(APIView):

    permission_classes = [IsAdmin]

    def get(self, request, *args, **kwargs):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Студенты в общежитиях"

        headers = ["S Студента", "Фамилия", "Имя", "Отчество", "Общежитие", "Комната", "ID Заявления", "Ордер", "ИИН"]
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
                student_dorm.order.url if student_dorm.order else "Нет",
                getattr(student, 'iin', "Нет данных"),
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





class AssignRoomAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):

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



class ClearStudentInDormView(APIView):
    permission_classes = [IsSuperAdmin]  # только админы

    def delete(self, request):
        deleted_count, _ = StudentInDorm.objects.all().delete()
        return Response(
            {'detail': f'Удалено {deleted_count} записей StudentInDorm'},
            status=status.HTTP_204_NO_CONTENT
        )




from rest_framework import serializers, viewsets, permissions
from django.contrib.contenttypes.models import ContentType
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Q

User = get_user_model()


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
    # permission_classes = [IsAdmin]
    ordering_fields = ['timestamp']
    ordering = ['-timestamp']

    def get_allowed_user_ids(self):
        cache_key = 'audit_log_allowed_user_ids'
        allowed_ids = cache.get(cache_key)

        if allowed_ids is None:
            allowed_ids = list(
                User.objects.filter(
                    Q(admin__isnull=False) | Q(is_superuser=True)
                ).values_list('pk', flat=True)
            )
            cache.set(cache_key, allowed_ids, timeout=60 * 60 * 24)

        return allowed_ids

    def get_queryset(self):
        return (
            LogEntry.objects
            .filter(actor_id__in=self.get_allowed_user_ids())
            .select_related('actor')
            .only(
                'id',
                'actor_id',
                'action',
                'timestamp',
            )
        )