from dorm.models import EvidenceType
from django.core.mail import send_mail
from django.conf import settings
from sentence_transformers import SentenceTransformer
import re
from sklearn.metrics.pairwise import cosine_similarity



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


model = SentenceTransformer('all-MiniLM-L6-v2')

# Функция для поиска номера общежития в вопросе
def extract_dorm_number(text):
    match = re.search(r'общежитие\s*№?\s*(\d+)', text)
    if match:
        return match.group(1)
    return None

# Функция для распознавания эмоций
def detect_emotion(question):
    emotions_keywords = {
        "боюсь": "Понимаю ваше волнение. Всё решаемо — советую обратиться к куратору или в деканат, они обязательно помогут.",
        "страшно": "Понимаю ваше волнение. Всё решаемо — советую обратиться к куратору или в деканат, они обязательно помогут.",
        "переживаю": "Понимаю ваше волнение. Всё решаемо — советую обратиться к куратору или в деканат, они обязательно помогут.",
        "не дали общагу": "Не переживайте! Обратитесь в отдел студенческого проживания для дополнительной консультации.",
        "не получил место": "Не переживайте! Обратитесь в отдел студенческого проживания для дополнительной консультации.",
        "что дальше делать": "Вы можете подать апелляцию или обратиться в приёмную комиссию для повторной консультации.",
        "что теперь": "Вы можете подать апелляцию или обратиться в приёмную комиссию для повторной консультации.",
        "тупой": "Мне жаль, что вы расстроены. Давайте попробуем найти решение вместе.",
        "плохой бот": "Мне жаль, что вы расстроены. Давайте попробуем найти решение вместе.",
    }
    for key, response in emotions_keywords.items():
        if key in question.lower():
            return response
    return None

# Основная функция поиска ответа
def find_best_answer(question):
    # Сначала определяем эмоцию
    emotion_answer = detect_emotion(question)
    if emotion_answer:
        return emotion_answer

    from dorm.models import KnowledgeBase
    entries = KnowledgeBase.objects.all()
    question_lower = question.lower()

    # Поиск по номеру общежития
    number = extract_dorm_number(question_lower)
    if number:
        for entry in entries:
            if number in entry.question_keywords:
                return entry.answer

    # Прямое вхождение
    for entry in entries:
        if entry.question_keywords.lower() in question_lower:
            return entry.answer

    # Векторное сравнение
    user_vector = model.encode([question])
    best_answer = ""
    best_score = 0.0
    for entry in entries:
        entry_vector = model.encode([entry.question_keywords])
        score = cosine_similarity(user_vector, entry_vector)[0][0]
        if score > best_score:
            best_score = score
            best_answer = entry.answer

    if best_score < 0.5:
        return None  # если очень плохое совпадение — звать оператора

    return best_answer
