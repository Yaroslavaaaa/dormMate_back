# dorm/utils.py

import re
import torch
from pathlib import Path
from django.conf import settings
from django.core.mail import send_mail
from sentence_transformers import SentenceTransformer
from sklearn.metrics.pairwise import cosine_similarity
from .ai_model import generate_answer_from_model  # наш локальный AI
from dorm.models import EvidenceType, KnowledgeBase

# 📬 Email-уведомление
def send_email_notification(email, message):
    send_mail(
        subject="Уведомление от системы",
        message=message,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=[email],
        fail_silently=False,
    )

# 📊 Подсчёт баллов заявки (пример)
def calculate_application_score(application):
    score = 0
    evidences = {e.evidence_type.code: e for e in application.evidences.filter(approved=True)}
    for et in EvidenceType.objects.all():
        if et.code == 'gpa' and application.student.course != '1':
            ev = evidences.get('gpa')
            val = ev.numeric_value if ev and ev.numeric_value is not None else application.gpa
            if val is not None:
                score += et.priority * float(val)
        elif et.code == 'ent_result' and application.student.course == '1':
            ev = evidences.get('ent_result')
            val = ev.numeric_value if ev and ev.numeric_value is not None else application.ent_result
            if val is not None:
                score += et.priority * float(val)
        else:
            ev = evidences.get(et.code)
            if et.data_type == 'file' and ev and ev.file:
                score += et.priority
            elif et.data_type == 'numeric':
                val = (
                    ev.numeric_value if ev and ev.numeric_value is not None
                    else getattr(application, et.auto_fill_field, None)
                    or getattr(application.student, et.auto_fill_field, None)
                )
                if val is not None:
                    score += et.priority * float(val)
    return score

# 🧠 Векторная модель для семантики
vector_model = SentenceTransformer("all-MiniLM-L6-v2")

# 😟 Эмоциональный фильтр
def detect_emotion(q: str) -> str | None:
    mapping = {
        "боюсь": "Понимаю ваше волнение — советую обратиться к деканату.",
        "страшно": "Всё решаемо — напишите в приёмную комиссию.",
        "переживаю": "Не волнуйтесь, мы поможем!",
        "не дали общагу": "Обратитесь в отдел студенческого проживания.",
        "что дальше делать": "Можно подать апелляцию или уточнить статус заявки.",
        "плохой бот": "Мне жаль, давайте попробуем снова.",
    }
    text = q.lower()
    for k, resp in mapping.items():
        if k in text:
            return resp
    return None

# 🏠 Вычленение номера общежития
def extract_dorm_number(text: str) -> str | None:
    m = re.search(r"общежитие\s*№?\s*(\d+)", text, re.IGNORECASE)
    return m.group(1) if m else None

# 🎯 Основная функция ответа
def find_best_answer(question: str) -> str:
    ql = question.strip()
    # 1) эмоции
    emo = detect_emotion(ql)
    if emo:
        return emo

    # 2) База знаний
    entries = KnowledgeBase.objects.all()
    num = extract_dorm_number(ql)
    if num:
        for e in entries:
            if num in e.question_keywords:
                return e.answer

    # 3) точное вхождение
    for e in entries:
        if e.question_keywords.lower() in ql.lower():
            return e.answer

    # 4) векторный поиск
    uv = vector_model.encode([ql])
    best, score = "", 0.0
    for e in entries:
        ev = vector_model.encode([e.question_keywords])
        s = cosine_similarity(uv, ev)[0][0]
        if s > score:
            score, best = s, e.answer
    if score >= 0.5:
        return best

    # 5) если ничего не подошло — AI
    return generate_answer_from_model(ql)
