from dorm.models import EvidenceType
from django.core.mail import send_mail
from django.conf import settings




def send_email_notification(email, message):
    send_mail(
        subject="Уведомление от системы",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )



def calculate_application_score(application):
    score = 0
    # Собираем одобренные доказательства в словарь (ключ – код EvidenceType)
    evidences = {
        e.evidence_type.code: e
        for e in application.evidences.filter(approved=True)
    }

    for et in EvidenceType.objects.all():
        if et.code == 'gpa':
            if application.student.course != '1':
                evidence = evidences.get('gpa')
                if evidence and evidence.numeric_value is not None:
                    score += et.priority * float(evidence.numeric_value)
                elif application.gpa is not None:
                    score += et.priority * float(application.gpa)
        elif et.code == 'ent_result':
            if application.student.course == '1':
                evidence = evidences.get('ent_result')
                if evidence and evidence.numeric_value is not None:
                    score += et.priority * float(evidence.numeric_value)
                elif application.ent_result is not None:
                    score += et.priority * float(application.ent_result)
        else:
            evidence = evidences.get(et.code)
            if et.data_type == 'file':
                if evidence and evidence.file:
                    score += et.priority
            elif et.data_type == 'numeric':
                if evidence and evidence.numeric_value is not None:
                    score += et.priority * float(evidence.numeric_value)
                elif et.auto_fill_field:
                    auto_value = (
                            getattr(application, et.auto_fill_field, None) or
                            getattr(application.student, et.auto_fill_field, None)
                    )
                    if auto_value is not None:
                        score += et.priority * float(auto_value)
    return score
