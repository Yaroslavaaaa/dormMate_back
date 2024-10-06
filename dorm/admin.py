from django.contrib import admin

from .models import *

# Register your models here.


admin.site.register(Student)
admin.site.register(Dorm)
admin.site.register(Application)
admin.site.register(Region)
admin.site.register(TestQuestion)

