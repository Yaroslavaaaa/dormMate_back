from django.contrib import admin
import pandas as pd
from django.http import HttpResponse

from .models import *

# Register your models here.


admin.site.register(Student)
admin.site.register(Admin)
admin.site.register(User)
admin.site.register(Dorm)
admin.site.register(Application)
admin.site.register(Region)
admin.site.register(TestQuestion)
admin.site.register(QuestionAnswer)
def export_students_in_dorm_to_excel(modeladmin, request, queryset):
    data = []
    for student in queryset:
        data.append({
            'student_id': student.student_id,
            'dorm_id': student.dorm_id,
            'room': student.room,
            'application_id': student.application_id,
            'order': student.order.url if student.order else None
        })

    df = pd.DataFrame(data)

    response = HttpResponse(content_type='application/vnd.ms-excel')
    response['Content-Disposition'] = 'attachment; filename="students_in_dorm.xlsx"'

    df.to_excel(response, index=False, sheet_name='StudentsInDorm')

    return response

export_students_in_dorm_to_excel.short_description = "Выгрузить выбранные записи в Excel"

@admin.register(StudentInDorm)
class StudentInDormAdmin(admin.ModelAdmin):
    list_display = ('student_id', 'dorm_id', 'room', 'application_id', 'order')
    actions = [export_students_in_dorm_to_excel]

class ApplicationAdmin(admin.ModelAdmin):
    list_display = (
        'id',
        'student',
        'dormitory_choice',
        'status',
        'approval',
        'created_at',
    )
    list_filter = ('status', 'approval', 'dormitory_choice')
    search_fields = ('student_first_name', 'studentlast_name', 'dormitory_choice_name', 'status')
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

