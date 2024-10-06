"""
URL configuration for dormMate project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/5.1/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from dorm.views import *

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/studentlist', StudentViewSet.as_view()),
    path('api/v1/dormlist', DormViewSet.as_view()),
    path('api/v1/upload-excel/', ExcelUploadView.as_view()),
    path('api/v1/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/token/verify/', TokenVerifyView.as_view(), name='token_'),
    path('api/v1/create_application/', CreateApplicationView.as_view(), name='create_application'),
    path('api/v1/test/<int:pk>/', TestView.as_view(), name='test'),
]
