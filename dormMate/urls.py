from django.contrib import admin
from django.conf import settings
from django.conf.urls.static import static
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView
from dorm.views import *
from dorm.studentViews import *
from dorm.adminViews import *

router = DefaultRouter()
router.register(r'dorms', DormsViewSet, basename='dorm')
router.register(r'students', StudentsViewSet, basename='students')
router.register(r'dorm-images', DormImageViewSet, basename='dorm-images')
router.register(r'admins', AdminViewSet, basename='admin')
router.register(r'keywords', KeywordViewSet, basename='keyword')
router.register(r'evidence-types', EvidenceTypeViewSet, basename='evidencetype')
router.register(r'audit-log', AuditLogViewSet, basename='audit-log')

urlpatterns = [
    path('admin/', admin.site.urls),

    # applications
    path('api/v1/create_application/', CreateApplicationView.as_view(), name='create_application'),
    path('api/v1/test/', TestView.as_view(), name='test'),
    path('api/v1/application_status/', ApplicationStatusView.as_view(), name='application_status'),
    path('api/v1/upload_payment_screenshot/', UploadPaymentScreenshotView.as_view(), name='upload_payment_screenshot'),
    path('api/v1/applications/<int:pk>/document/<slug:evidence_code>/', PDFView.as_view(), name='application-pdf'),
    path('api/v1/evidences/<int:pk>/update-status/', UpdateEvidenceStatusAPIView.as_view(),
         name='update-evidence-status'),
    path('api/v1/applications/<int:pk>/payment-screenshot/', PaymentScreenshotView.as_view(),
         name='payment_screenshot'),
    path('api/v1/questionlist', TestQuestionViewSet.as_view()),

    # students
    path('api/v1/upload-avatar/', AvatarUploadView.as_view(), name='upload-avatar'),
    path('api/v1/studentdetail/', StudentDetailView.as_view(), name='student_detail'),
    path('api/v1/application/', UserApplicationView.as_view(), name='application'),

    # admins
    path('api/v1/distribute-students2/', DistributeStudentsAPIView2.as_view(), name='distribute-students'),
    path('api/v1/issue-order/', IssueOrderAPIView.as_view(), name='issue_order'),
    path('api/v1/export-students/', ExportStudentInDormExcelView.as_view(), name='export_students_excel'),
    path('api/v1/reminder/partial-payment/', SendPartialPaymentReminderAPIView.as_view(),
         name='partial_payment_reminder'),
    path('api/v1/generate-selection/', GenerateSelectionAPIView.as_view(), name='generate-selection'),
    path('api/v1/notify-approved/', NotifyApprovedStudentsAPIView.as_view(), name='notify-approved'),
    path('api/v1/student-in-dorm/', StudentInDormView.as_view(), name='student-in-dorm'),
    path('api/v1/payment-confirmation/', PaymentConfirmationAPIView.as_view(), name='payment-confirmation'),
    path('api/v1/assign-room/', AssignRoomAPIView.as_view(), name='assign_room'),
    path('api/v1/upload-excel/', ExcelUploadView.as_view()),
    path('api/v1/cleardormassignments/', ClearStudentInDormView.as_view(), name='clear_dorm_assignments'),
    path('api/v1/applications/<int:application_id>/delete/', DeleteStudentApplicationAPIView.as_view(),
         name='delete_application'),
    path('api/v1/applications/<int:application_id>/approve/', ApproveStudentApplicationAPIView.as_view(),
         name='approve_application'),
    path('api/v1/applications/<int:application_id>/reject/', RejectStudentApplicationAPIView.as_view(),
         name='approve_application'),
    path('api/v1/applications/', ApplicationListView.as_view(), name='application-list'),

    # dorms
    path('api/v1/dorms/costs/', DormCostListView.as_view(), name='dorm-cost-list'),

    # all

    # auth
    path('api/v1/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    path('api/v1/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('api/v1/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    path('api/v1/custom_token/', CustomTokenObtainView.as_view(), name='custom_token_obtain'),
    path("api/v1/logout/", LogoutView.as_view(), name="logout"),
    path('api/v1/change_password/', ChangePasswordView.as_view(), name='change_password'),

    # chat
    path('api/v1/student/chats/', StudentChatListView.as_view(), name='student-chat-list'),
    path('api/v1/chats/', ChatListView.as_view(), name='chat-list'),
    path('api/v1/student/chats/create/', CreateChatView.as_view(), name='create-chat'),
    path('api/v1/chats/<int:chat_id>/messages/', MessageListView.as_view(), name='chat-messages'),
    path('api/v1/chats/<int:chat_id>/send/', SendMessageView.as_view(), name='send-message'),
    path('api/v1/chats/<int:chat_id>/end/', EndChatView.as_view(), name='end-chat'),
    path('api/v1/chats/<int:id>/', ChatDetailView.as_view(), name='chat-detail'),

    # notifications
    path('api/v1/notifications/', NotificationListView.as_view(), name='notification-list'),
    path('api/v1/notifications/<int:pk>/read/', MarkNotificationAsReadView.as_view(), name='notification-read'),
    path('api/v1/notifications/request-admin/', RequestAdminView.as_view(), name='request-admin'),
    path('api/v1/notifications/admin/', AdminNotificationListView.as_view(), name='admin-notifications'),

    # other
    path("api/v1/usertype/", UserTypeView.as_view(), name="usertype"),
    path('api/v1/', include(router.urls)),
    path('api/v1/regions/', RegionListView.as_view(), name='region-list'),
    path('knowledge/', KnowledgeBaseListView.as_view(), name='knowledge-base'),
    path('api/v1/questions/', QuestionView.as_view(), name='question'),
    path('api/v1/evidence-types/', EvidenceTypeListAPIView.as_view(), name='evidence-types-list'),
    path('api/v1/student/application/', StudentApplicationUpdateView.as_view(), name='student-application-update'),
    path('api/v1/my-admin-role/', MyAdminRoleAPIView.as_view(), name='my-admin-role'),
    path('api/v1/application/evidences/', ApplicationEvidenceListView.as_view(), name='application-evidences'),

]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
