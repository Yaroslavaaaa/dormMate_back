from django.db.models.signals import pre_save
from django.dispatch import receiver
from googletrans import Translator
from .models import Dorm, TestQuestion, EvidenceType, Notification, QuestionAnswer, KnowledgeBase

translator = Translator()

@receiver(pre_save, sender=Dorm)
def translate_dorm_fields(sender, instance, **kwargs):
    if instance.name_ru:
        if not instance.name_kk:
            instance.name_kk = translator.translate(instance.name_ru, dest='kk').text
        if not instance.name_en:
            instance.name_en = translator.translate(instance.name_ru, dest='en').text
    if instance.description_ru:
        if not instance.description_kk:
            instance.description_kk = translator.translate(instance.description_ru, dest='kk').text
        if not instance.description_en:
            instance.description_en = translator.translate(instance.description_ru, dest='en').text

@receiver(pre_save, sender=TestQuestion)
def translate_testquestion_fields(sender, instance, **kwargs):
    if instance.question_text_ru:
        if not instance.question_text_kk:
            instance.question_text_kk = translator.translate(instance.question_text_ru, dest='kk').text
        if not instance.question_text_en:
            instance.question_text_en = translator.translate(instance.question_text_ru, dest='en').text
    for v in ['a', 'b', 'c']:
        field_ru = getattr(instance, f'answer_variant_{v}_ru', None)
        if field_ru:
            for lang in ['kk', 'en']:
                field_lang = f'answer_variant_{v}_{lang}'
                if not getattr(instance, field_lang):
                    setattr(instance, field_lang, translator.translate(field_ru, dest=lang).text)


@receiver(pre_save, sender=Notification)
def translate_notification_fields(sender, instance, **kwargs):
    if instance.message_ru:
        if not instance.message_kk:
            instance.message_kk = translator.translate(instance.message_ru, dest='kk').text
        if not instance.message_en:
            instance.message_en = translator.translate(instance.message_ru, dest='en').text

@receiver(pre_save, sender=QuestionAnswer)
def translate_questionanswer_fields(sender, instance, **kwargs):
    if instance.question_ru:
        if not instance.question_kk:
            instance.question_kk = translator.translate(instance.question_ru, dest='kk').text
        if not instance.question_en:
            instance.question_en = translator.translate(instance.question_ru, dest='en').text
    if instance.answer_ru:
        if not instance.answer_kk:
            instance.answer_kk = translator.translate(instance.answer_ru, dest='kk').text
        if not instance.answer_en:
            instance.answer_en = translator.translate(instance.answer_ru, dest='en').text

