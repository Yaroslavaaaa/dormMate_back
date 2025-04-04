from django.contrib import admin
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from dorm.views import *



router = DefaultRouter()
router.register(r'dorms', DormsViewSet, basename='dorm')
router.register(r'students', StudentsViewSet, basename='students')

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/v1/studentlist', StudentViewSet.as_view()),
    path('api/v1/dormlist', DormView.as_view()),
    path('api/v1/questionlist', TestQuestionViewSet.as_view()),
    path('api/v1/upload-excel/', ExcelUploadView.as_view()),
    path('api/v1/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('api/v1/dorms/costs/', DormCostListView.as_view(), name='dorm-cost-list'),
    path('api/v1/create_application/', CreateApplicationView.as_view(), name='create_application'),
    path('api/v1/test/', TestView.as_view(), name='test'),
    path('api/v1/custom_token/', CustomTokenObtainView.as_view(), name='custom_token_obtain'),
    path('api/v1/application_status/', ApplicationStatusView.as_view(), name='application_status'),
    path('api/v1/upload_payment_screenshot/', UploadPaymentScreenshotView.as_view(), name='upload_payment_screenshot'),
    # path('questions/', QuestionListView.as_view(), name='question-list'),
    # path('questions/create/', QuestionCreateView.as_view(), name='question-create'),
    # path('answers/create/', AnswerCreateView.as_view(), name='answer-create'),    path('api/v1/distribute-students/', DistributeStudentsAPIView.as_view(), name='distribute-students'),
    path('api/v1/distribute-students2/', DistributeStudentsAPIView2.as_view(), name='distribute-students'),
    path('api/v1/studentdetail/', StudentDetailView.as_view(), name='student_detail'),
    path("api/v1/logout/", LogoutView.as_view(), name="logout"),
    path("api/v1/usertype/", UserTypeView.as_view(), name="usertype"),
    path('api/v1/change_password/', ChangePasswordView.as_view(), name='change_password'),
    path('api/v1/applications', ApplicationViewSet.as_view(), name='applications'),
    path('api/v1/applications/<int:application_id>/delete/', DeleteStudentApplicationAPIView.as_view(),name='delete_application'),
    path('api/v1/applications/<int:application_id>/approve/',ApproveStudentApplicationAPIView.as_view(), name='approve_application'),
    path('api/v1/applications/<int:application_id>/reject/',RejectStudentApplicationAPIView.as_view(), name='approve_application'),
    path('api/v1/applications/<int:application_id>/change-dormitory/', ChangeStudentDormitoryAPIView.as_view(),name='change_dormitory'),
    path('api/v1/export-students/', ExportStudentInDormExcelView.as_view(), name='export_students_excel'),
    path('api/v1/applications/<int:pk>/', ApplicationDetailView.as_view(), name='application-detail'),
    path('api/v1/applications/<int:pk>/files/<str:field_name>/', PDFView.as_view(), name='pdf-view'),
    path('api/v1/applications/<int:pk>/payment-screenshot/', PaymentScreenshotView.as_view(), name='payment_screenshot'),
    path('api/v1/', include(router.urls)),
    path('api/v1/applications/', ApplicationListView.as_view(), name='application-list'),
    path('api/v1/regions/', RegionListView.as_view(), name='region-list'),

    path('api/v1/questions/', QuestionView.as_view(), name='question'),
    path('api/v1/student/chats/', StudentChatListView.as_view(), name='student-chat-list'),
    path('api/v1/chats/', ChatListView.as_view(), name='chat-list'),
    # Отправка сообщения в конкретный чат
    # Завершение чата
    path('api/v1/questions/', QuestionView.as_view(), name='questions'),
    path('api/v1/notifications/', NotificationListView.as_view(), name='notification-list'),
    path('api/v1/notifications/<int:pk>/read/', MarkNotificationAsReadView.as_view(), name='notification-read'),
    path('api/v1/notifications/request-admin/', RequestAdminView.as_view(), name='request-admin'),

    path('api/v1/student/chats/create/', CreateChatView.as_view(), name='create-chat'),
    path('api/v1/chats/<int:chat_id>/messages/', MessageListView.as_view(), name='chat-messages'),
    path('api/v1/chats/<int:chat_id>/send/', SendMessageView.as_view(), name='send-message'),
    path('api/v1/chats/<int:chat_id>/end/', EndChatView.as_view(), name='end-chat'),
    path('api/v1/notifications/admin/', AdminNotificationListView.as_view(), name='admin-notifications'),


]
