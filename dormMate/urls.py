from django.contrib import admin
from django.urls import path
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from dorm.views import *

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/studentlist', StudentViewSet.as_view()),
    path('api/v1/dormlist', DormViewSet.as_view()),
    path('api/v1/questionlist', TestQuestionViewSet.as_view()),
    path('api/v1/upload-excel/', ExcelUploadView.as_view()),
    path('api/v1/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('api/v1/create_application/', CreateApplicationView.as_view(), name='create_application'),
    path('api/v1/test/<int:pk>/', TestView.as_view(), name='test'),
    path('api/v1/custom_token/', CustomTokenObtainView.as_view(), name='custom_token_obtain'),
    path('api/v1/application_status/<int:student_id>/', ApplicationStatusView.as_view(), name='application_status'),
    path('api/v1/upload_payment_screenshot/<int:student_id>/', UploadPaymentScreenshotView.as_view(), name='upload_payment_screenshot'),
    path('api/v1/web_assistant/', QuestionViewSet.as_view(), name='web_assistant'),
    path('api/v1/web_assistant/questions/<int:pk>/', AnswerDetailView.as_view(), name='answer_detail'),
    path('api/v1/web_assistant/questions/', QuestionAnswerViewSet.as_view(), name='questions'),
]
