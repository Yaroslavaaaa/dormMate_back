# dorm/admin.py
from django.contrib import admin
import pandas as pd
from django.http import HttpResponse

from .models import *


class RoomInline(admin.TabularInline):
    model = Room
    extra = 1
    fields = ('number', 'capacity')
    verbose_name = "Комната"
    verbose_name_plural = "Комнаты"


@admin.register(Room)
class RoomAdmin(admin.ModelAdmin):
    list_display = ('dorm', 'number', 'capacity', 'occupied_places', 'floor')
    # Заменили 'dorm__name' на 'dorm__name_ru'
    list_filter  = ('dorm__name_ru',)
    # Заменили 'dorm__name' на 'dorm__name_ru'
    search_fields = ('number', 'dorm__name_ru')

    def occupied_places(self, obj):
        return obj.occupants.count()
    occupied_places.short_description = 'Занято мест'

admin.site.register(Student)
class EvidenceKeywordInline(admin.TabularInline):
    model = EvidenceKeyword
    extra = 1


@admin.register(EvidenceType)
class EvidenceTypeAdmin(admin.ModelAdmin):
    list_display = ('name', 'code', 'priority', 'data_type')
    search_fields = ('name', 'code')
    inlines = [EvidenceKeywordInline]


@admin.register(Keyword)
class KeywordAdmin(admin.ModelAdmin):
    list_display = ('keyword',)
    search_fields = ('keyword',)


@admin.register(ApplicationEvidence)
class ApplicationEvidenceAdmin(admin.ModelAdmin):
    list_display = ('application', 'evidence_type', 'created_at')
    list_filter = ('evidence_type',)




class DormImageInline(admin.TabularInline):
    model = DormImage
    extra = 1


@admin.register(Dorm)
class DormAdmin(admin.ModelAdmin):
    inlines = [DormImageInline, RoomInline]


admin.site.register(DormImage)
admin.site.register(Region)
admin.site.register(TestQuestion)
admin.site.register(QuestionAnswer)
admin.site.register(Admin)
admin.site.register(User)


def export_students_in_dorm_to_excel(modeladmin, request, queryset):
    data = []
    for student_in_dorm in queryset:
        data.append({
            'student_id': student_in_dorm.student.id,
            'dorm_id': student_in_dorm.room.dorm.id if student_in_dorm.room else None,
            'room': student_in_dorm.room.number if student_in_dorm.room else None,
            'application_id': student_in_dorm.application.id if student_in_dorm.application else None,
            'order': student_in_dorm.order.url if student_in_dorm.order else None
        })

    df = pd.DataFrame(data)
    response = HttpResponse(content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = 'attachment; filename="students_in_dorm.xlsx"'
    df.to_excel(response, index=False, sheet_name='StudentsInDorm')
    return response

export_students_in_dorm_to_excel.short_description = "Выгрузить выбранные записи в Excel"


@admin.register(StudentInDorm)
class StudentInDormAdmin(admin.ModelAdmin):
    list_display = ('student', 'application', 'room', 'group', 'assigned_at')
    list_filter  = ('room__dorm__name_ru', 'group')
    search_fields = ('student__email', 'room__number', 'application__student__email')
    ordering = ('-assigned_at',)
    actions  = [export_students_in_dorm_to_excel]


@admin.register(Chat)
class ChatAdmin(admin.ModelAdmin):
    list_display = ('id', 'student', 'status', 'created_at')
    list_filter  = ('status', 'created_at')
    search_fields = ('student__s', 'status')


@admin.register(Message)
class MessageAdmin(admin.ModelAdmin):
    list_display = ('id', 'sender', 'receiver', 'content', 'timestamp')
    list_filter  = ('timestamp',)
    search_fields = ('content',)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'recipient', 'message_ru', 'created_at', 'is_read')
    list_filter  = ('created_at', 'is_read')
    search_fields = ('recipient__s', 'message_ru')


@admin.register(KnowledgeBase)
class KnowledgeBaseAdmin(admin.ModelAdmin):
    list_display = ('question_keywords', 'answer')
    search_fields = ('question_keywords', 'answer')


@admin.register(GlobalSettings)
class GlobalSettingsAdmin(admin.ModelAdmin):
    list_display = ('id', 'allow_application_edit')
    list_editable = ('allow_application_edit',)
    list_display_links = ('id',)
    fieldsets = (
        (None, {
            'fields': ('allow_application_edit',),
            'description': 'Глобальная настройка: разрешить ли студентам редактировать заявки'
        }),
    )


@admin.register(Application)
class ApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'student',
        'dormitory_cost',  # заменили несуществующее поле dormitory_choice на dormitory_cost
        'status',
        'approval',
        'created_at',
    )
    list_filter = ('status', 'approval', 'dormitory_cost')
    # Заменили несуществующие search_fields на реальные:
    # поиск по имени/фамилии студента и статусу
    search_fields = ('student__first_name', 'student__last_name', 'status')
    actions = ['approve_application', 'reject_application']

    def approve_application(self, request, queryset):
        for application in queryset:
            print(f"Заявка {application.id} одобрена администратором {request.user}")
        queryset.update(status='approved', approval=True)
        self.message_user(request, "Выбранные заявки одобрены.")

    def reject_application(self, request, queryset):
        for application in queryset:
            print(f"Заявка {application.id} отклонена администратором {request.user}")
        queryset.update(status='rejected', approval=False)
        self.message_user(request, "Выбранные заявки отклонены.")

    approve_application.short_description = "Одобрить заявки"
    reject_application.short_description = "Отклонить заявки"

    def save_model(self, request, obj, form, change):
        if not change:
            obj.status = 'pending'
        super().save_model(request, obj, form, change)

    def delete_model(self, request, obj):
        print(f"Заявка {obj.id} удалена администратором {request.user}")
        super().delete_model(request, obj)
