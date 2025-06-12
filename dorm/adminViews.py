from rest_framework import status
from rest_framework.views import APIView
from rest_framework.response import Response
import pandas as pd
from thefuzz import process
from datetime import datetime
from .serializers import *
from django.http import HttpResponse
from io import BytesIO
import openpyxl
from rest_framework.permissions import IsAuthenticated
from django.db.models import Sum, Count, F
from django.db import transaction
from collections import defaultdict
import json
from rest_framework import viewsets, permissions
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db.models import Q

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

from fuzzywuzzy import process

from datetime import datetime
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
                print(f"Processing student: {row['student_s']} - Password generated: {password}")

                gpa = row.get('gpa', None)
                if gpa:
                    gpa = float(gpa)
                else:
                    gpa = None

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
                        'gpa': gpa
                    }
                )

                print(f"Student created: {created}. Current student password: {student.password}")

                if not student.password:
                    print(f"Setting password for student {student.s}")
                    student.set_password(password)
                else:
                    print(f"Password already set for student {student.s}")

                student.save()
                print(f"Password for student {student.s} set successfully.")

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
        approved_applications = list(Application.objects.filter(
            approval=True, status="approved"
        ))

        dorm_capacities = Dorm.objects.values('cost').annotate(total_capacity=Sum('total_places'))
        capacity_by_cost = {entry['cost']: entry['total_capacity'] for entry in dorm_capacities}

        apps_by_cost = defaultdict(list)
        for app in approved_applications:
            apps_by_cost[app.dormitory_cost].append(app)

        sorted_costs = sorted(capacity_by_cost.keys(), reverse=True)

        transferred_app_ids = []

        for i in range(len(sorted_costs) - 1):
            cost = sorted_costs[i]
            next_cost = sorted_costs[i + 1]
            current_apps = apps_by_cost[cost]
            capacity = capacity_by_cost.get(cost, 0)
            overflow = len(current_apps) - capacity

            if overflow > 0:
                next_capacity = capacity_by_cost.get(next_cost, 0)
                current_next_count = len(apps_by_cost[next_cost])
                available_lower = next_capacity - current_next_count

                to_transfer_count = min(overflow, available_lower) if available_lower > 0 else 0

                if to_transfer_count > 0:
                    current_apps_sorted = sorted(current_apps, key=lambda app: calculate_application_score(app))
                    apps_to_transfer = current_apps_sorted[:to_transfer_count]

                    for app in apps_to_transfer:
                        old_cost = app.dormitory_cost
                        app.dormitory_cost = next_cost
                        app.save()
                        send_email_notification(
                            app.student.email,
                            f"Здравствуйте, {app.student.first_name}! К сожалению, вам не было предоставлено место за {old_cost}. Вместо этого предоставляем место за {next_cost}."
                        )
                        transferred_app_ids.append(app.id)
                        apps_by_cost[cost].remove(app)
                        apps_by_cost[next_cost].append(app)

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
        excel_file = request.FILES.get('file') or request.FILES.get('excel_file')
        if not excel_file:
            return Response(
                {"detail": "Excel-файл обязателен для проверки данных студентов."},
                status=status.HTTP_400_BAD_REQUEST
            )

        try:
            df = pd.read_excel(excel_file)
        except Exception as e:
            return Response(
                {"detail": f"Ошибка при чтении Excel-файла: {e}"},
                status=status.HTTP_400_BAD_REQUEST
            )

        df.columns = (
            df.columns
            .astype(str)
            .str.strip()
            .str.lower()
            .str.replace(r'\s+', '_', regex=True)
        )

        valid_payments = {}
        for _, row in df.iterrows():
            raw_iin = row.get('iin') or row.get('иин')
            if pd.isna(raw_iin):
                continue
            if isinstance(raw_iin, (int, float)):
                iin = str(int(raw_iin)).zfill(12)
            else:
                iin = str(raw_iin).strip().zfill(12)

            raw_paid = row.get('оплачено')
            if pd.isna(raw_paid):
                continue

            paid_int = int(round(float(raw_paid)))
            valid_payments[iin] = paid_int

        for iin, paid in valid_payments.items():
            print(f"  IIN={iin} paid={paid}")

        approved_apps = Application.objects.filter(
            approval=True,
            payment_screenshot__isnull=False
        ).exclude(payment_screenshot='')

        added_students = []
        with transaction.atomic():
            for app in approved_apps:
                student_iin = str(app.student.iin or '').strip().zfill(12)

                if student_iin not in valid_payments:
                    continue

                paid_int = valid_payments[student_iin]
                cost = app.dormitory_cost
                is_full = (paid_int == cost)

                Application.objects.filter(pk=app.pk).update(
                    is_full_payment=is_full,
                    status='awaiting_order'
                )

                if not StudentInDorm.objects.filter(application=app).exists():
                    record = StudentInDorm.objects.create(
                        student=app.student,
                        application=app,
                        room=None,
                        group=None
                    )
                    added_students.append({
                        "student_iin": student_iin,
                        "application_id": app.id,
                        "paid": paid_int,
                        "is_full_payment": is_full
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
        base_qs = Application.objects.filter(
            status='awaiting_order',
            approval=True
        )
        pending_qs = base_qs.filter(
            Q(dorm_assignment__isnull=True)
            | Q(dorm_assignment__room__isnull=True)
        ).select_related('student')

        if not pending_qs.exists():
            return Response(
                {"detail": "Нет студентов, ожидающих распределения."},
                status=status.HTTP_200_OK
            )

        cost_to_apps = defaultdict(list)
        for app in pending_qs:
            cost_to_apps[app.dormitory_cost].append(app)

        allocated_students = []
        group_counter = 1

        with transaction.atomic():
            for cost, apps in cost_to_apps.items():
                dorms = Dorm.objects.filter(cost=cost)
                if not dorms.exists():
                    continue

                priority_apps = [a for a in apps if a.needs_low_floor]
                normal_apps = [a for a in apps if not a.needs_low_floor]

                group_counter = self._assign_group(
                    priority_apps, dorms, group_counter,
                    allocated_students,
                    floor_max=2
                )

                group_counter = self._assign_group(
                    normal_apps, dorms, group_counter,
                    allocated_students,
                    floor_max=None
                )

        return Response({
            "detail": "Студенты успешно распределены по корпусам и комнатам.",
            "allocated_students": allocated_students
        }, status=status.HTTP_200_OK)

    def _assign_group(
            self, apps, dorms, start_group_counter,
            allocated_students, floor_max=None
    ):

        group_counter = start_group_counter

        male = [a for a in apps if a.student.gender and a.student.gender.upper() == 'M']
        female = [a for a in apps if a.student.gender and a.student.gender.upper() == 'F']

        for dorm in dorms:
            rooms_qs = Room.objects.filter(dorm=dorm).annotate(
                occupied=Count('room_occupants')
            ).order_by('-capacity', 'number')

            if floor_max is not None:
                rooms = [r for r in rooms_qs if r.floor and r.floor <= floor_max]
            else:
                rooms = list(rooms_qs)

            for room in rooms:
                free = room.capacity - room.occupied
                if free <= 0:
                    continue

                if len(male) >= free and len(female) >= free:
                    pool = male if len(male) >= len(female) else female
                elif len(male) >= free:
                    pool = male
                elif len(female) >= free:
                    pool = female
                else:
                    continue

                group = self.allocate_slot(pool, free)
                if not group:
                    continue

                for app in group:
                    pool.remove(app)
                    rec, created = StudentInDorm.objects.update_or_create(
                        application=app,
                        defaults={
                            'student': app.student,
                            'room': room,
                            'group': str(group_counter),
                        }
                    )
                    if created:
                        allocated_students.append({
                            "student_email": app.student.email,
                            "dorm_name": dorm.name_ru,
                            "room_number": room.number,
                            "group": str(group_counter)
                        })

                group_counter += 1

        leftovers = male + female
        if leftovers:
            rooms_qs = Room.objects.filter(dorm__in=dorms).annotate(
                occupied=Count('room_occupants')
            ).filter(
                occupied__lt=F('capacity')
            ).order_by('-capacity', 'number')

            if floor_max is not None:
                free_rooms = [r for r in rooms_qs if r.floor and r.floor <= floor_max]
            else:
                free_rooms = list(rooms_qs)

            for room in free_rooms:
                free = room.capacity - room.occupied
                for _ in range(free):
                    if not leftovers:
                        break
                    app = leftovers.pop(0)
                    rec, created = StudentInDorm.objects.update_or_create(
                        application=app,
                        defaults={
                            'student': app.student,
                            'room': room,
                            'group': str(group_counter),
                        }
                    )
                    if created:
                        allocated_students.append({
                            "student_email": app.student.email,
                            "dorm_name": room.dorm.name_ru,
                            "room_number": room.number,
                            "group": str(group_counter)
                        })
                group_counter += 1

        return group_counter

    def allocate_slot(self, candidate_pool, slot_size):

        if len(candidate_pool) < slot_size:
            return None

        groups = defaultdict(list)
        for app in candidate_pool:
            groups[app.test_result].append(app)

        for _, apps in groups.items():
            if len(apps) < slot_size:
                continue

            langs = defaultdict(list)
            for app in apps:
                answers = app.test_answers
                if isinstance(answers, str):
                    try:
                        answers = json.loads(answers)
                    except json.JSONDecodeError:
                        answers = []
                lang = answers[0] if isinstance(answers, list) and answers else None
                langs[lang].append(app)

            for code in ('A', 'B'):
                if len(langs.get(code, [])) >= slot_size:
                    return langs[code][:slot_size]
            return apps[:slot_size]

        sorted_groups = sorted(groups.values(), key=len, reverse=True)
        top_group = sorted_groups[0]
        selected = top_group[:]
        need = slot_size - len(selected)
        rest = [app for app in candidate_pool if app not in selected]
        if len(rest) < need:
            return None
        selected.extend(rest[:need])
        return selected if len(selected) == slot_size else None


class IssueOrderAPIView(APIView):
    permission_classes = [IsAdmin]

    def post(self, request, *args, **kwargs):
        waiting_records = StudentInDorm.objects.filter(
            application__status='awaiting_order'
        ).select_related('application', 'student', 'room__dorm')

        processed_students = []

        for record in waiting_records:
            application = record.application
            application.status = 'order'
            application.save(update_fields=['status'])

            student = record.student
            room = record.room
            dorm = room.dorm if room else None

            dorm_name = dorm.name_ru if dorm else "Не назначена"
            room_number = room.number if room else "—"

            try:
                send_mail(
                    subject="Ордер на заселение в общежитие",
                    message=(
                        f"Поздравляем, вам выдан ордер на заселение в общежитие!\n"
                        f"Общежитие: {dorm_name}\n"
                        f"Комната: {room_number}"
                    ),
                    from_email=settings.EMAIL_HOST_USER,
                    recipient_list=[student.email],
                    fail_silently=False,
                )
            except Exception as e:
                print(f"[IssueOrder] Ошибка отправки письма на {student.email}: {e}")

            processed_students.append({
                "student_email": student.email,
                "dorm_name": dorm_name,
                "room_number": room_number,
            })

        return Response({
            "detail": "Статусы обновлены и письма отправлены.",
            "processed_students": processed_students
        }, status=status.HTTP_200_OK)


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
        application.approval = True
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
        application.approval = False
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


from openpyxl import Workbook
from django.views import View

class ExportStudentsToExcelView(View):
    def get(self, request, *args, **kwargs):
        wb = Workbook()
        sheet = wb.active
        sheet.title = "Students"

        headers = ["S Студента", "Фамилия", "Имя", "Отчество", "Общежитие", "Комната", "ID Заявления", "Ордер", "ИИН"]
        sheet.append(headers)

        students = StudentInDorm.objects.select_related('student', 'room', 'room__dorm').all()

        for student_in_dorm in students:
            student = student_in_dorm.student
            dormitory = student_in_dorm.room.dorm if student_in_dorm.application else None
            room = student_in_dorm.room

            row = [
                student.s,
                student.last_name,
                student.first_name,
                student.middle_name,
                dormitory.name_ru if dormitory else '',
                room.number if room else '',
                student_in_dorm.application.id if student_in_dorm.application else '',
                student_in_dorm.order.name if student_in_dorm.order else '',
                student.iin if student.iin else ''
            ]
            sheet.append(row)

        response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        response['Content-Disposition'] = 'attachment; filename="students_export.xlsx"'

        wb.save(response)
        return response


class ExportStudentInDormExcelView(APIView):
    permission_classes = [IsAdmin]

    def get(self, request, *args, **kwargs):
        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Студенты в общежитиях"

        headers = ["S Студента", "Фамилия", "Имя", "Отчество", "Общежитие", "Комната", "ID Заявления", "Ордер", "ИИН"]
        sheet.append(headers)

        students_in_dorm = StudentInDorm.objects.select_related('student', 'application')

        for student_dorm in students_in_dorm:
            student = student_dorm.student
            row = [
                getattr(student, 's', "Нет данных"),
                getattr(student, 'last_name', "Нет данных"),
                getattr(student, 'first_name', "Нет данных"),
                getattr(student, 'middle_name', "Нет данных"),
                getattr(student_dorm.room.dorm, 'name_ru', "Нет данных"),
                student_dorm.room.number or "Нет данных",
                student_dorm.application.id if student_dorm.application else "Нет данных",
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
    permission_classes = [IsSuperAdmin]

    def delete(self, request):
        deleted_count, _ = StudentInDorm.objects.all().delete()
        return Response(
            {'detail': f'Удалено {deleted_count} записей StudentInDorm'},
            status=status.HTTP_204_NO_CONTENT
        )


User = get_user_model()


class AuditLogViewSet(viewsets.ReadOnlyModelViewSet):
    serializer_class = AuditLogSerializer
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
            .select_related('actor', 'content_type')
            .only(
                'id',
                'actor_id',
                'action',
                'timestamp',
                'content_type_id',
                'object_id',
                'object_repr',
                'changes',
                'content_type__app_label',
                'content_type__model',
                'actor__first_name',
                'actor__last_name',
            )
        )



class DormFloorsCountAPIView(APIView):
    """
    GET /api/v1/dorms/<pk>/floors_count/
    возвращает количество этажей для общежития с заданным pk.
    """

    def get(self, request, pk, *args, **kwargs):
        try:
            dorm = Dorm.objects.get(pk=pk)
        except Dorm.DoesNotExist:
            return Response(
                {"detail": "Общежитие не найдено."},
                status=status.HTTP_404_NOT_FOUND
            )

        count = dorm.floors_count()
        return Response({"floors_count": count}, status=status.HTTP_200_OK)