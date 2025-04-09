from django.test import TestCase
from django.core.files.uploadedfile import SimpleUploadedFile
from dorm.models import Region, Student, Application, EvidenceType, ApplicationEvidence
from dorm.serializers import ApplicationSerializer
# Импортируем функцию из нового места (например, из dorm/utils.py)
from dorm.utils import calculate_application_score

class ApplicationScoreTest(TestCase):
    def setUp(self):
        # Создаём объект Region для студентов
        self.region = Region.objects.create(region_name="Test Region")

        # Создаем EvidenceType для GPA, ЕНТ и дополнительный тип для файла (например, справка)
        self.gpa_et = EvidenceType.objects.create(
            name="GPA",
            code="gpa",
            priority=5,
            data_type="numeric",
            auto_fill_field="gpa"  # если поле не заполнено в заявке, будем брать значение из Application.gpa
        )
        self.ent_et = EvidenceType.objects.create(
            name="Результат ЕНТ",
            code="ent_result",
            priority=7,
            data_type="numeric"
        )
        self.orphan_et = EvidenceType.objects.create(
            name="Справка о сиротстве",
            code="orphan_certificate",
            priority=3,
            data_type="file"
        )

        # Создаем студентов.
        # Студент 1: не первого курса (например, 2-й курс)
        self.student1 = Student.objects.create(
            s="S22016167",
            first_name="Ivan",
            last_name="Ivanov",
            course="2",
            region=self.region,
            email="ivanov@example.com"
        )

        # Студент 2: первый курс
        self.student2 = Student.objects.create(
            s="S22016168",
            first_name="Petr",
            last_name="Petrov",
            course="1",
            region=self.region,
            email="petrov@example.com"
        )

    def test_score_for_first_course_using_ent(self):
        """
        Для студентов первого курса должен использоваться результат ЕНТ.
        Если evidence для ent_result не передан, берём значение из поля ent_result заявки.
        """
        application = Application.objects.create(
            student=self.student2,
            dormitory_cost=1000,
            ent_result=85,  # балл ЕНТ введён в заявке
            gpa=None,
            test_answers={},
            test_result="A"
        )
        score = calculate_application_score(application)
        expected = self.ent_et.priority * 85  # 7 * 85 = 595
        self.assertEqual(score, expected)

    def test_score_for_first_course_with_ent_evidence(self):
        """
        Если для первого курса задано evidence с результатом ЕНТ, он должен использоваться.
        """
        application = Application.objects.create(
            student=self.student2,
            dormitory_cost=1000,
            ent_result=None,
            gpa=None,
            test_answers={},
            test_result="A"
        )
        # Передаем evidence для ent_result
        ApplicationEvidence.objects.create(
            application=application,
            evidence_type=self.ent_et,
            numeric_value=80
        )
        score = calculate_application_score(application)
        expected = self.ent_et.priority * 80  # 7 * 80 = 560
        self.assertEqual(score, expected)

    def test_score_for_non_first_course_using_gpa(self):
        """
        Для студентов, не являющихся первокурсниками, используется GPA.
        Так как в модели Student нет поля GPA, значение должно передаваться в заявке.
        """
        application = Application.objects.create(
            student=self.student1,
            dormitory_cost=1000,
            ent_result=None,
            gpa=3.5,  # значение GPA передаём в заявке
            test_answers={},
            test_result="B"
        )
        score = calculate_application_score(application)
        expected = self.gpa_et.priority * 3.5  # 5 * 3.5 = 17.5
        self.assertEqual(score, expected)

    def test_score_with_additional_file_evidence(self):
        """
        Проверяем, что для файлового evidence (например, справка о сиротстве) прибавляется его приоритет.
        """
        application = Application.objects.create(
            student=self.student1,
            dormitory_cost=1000,
            ent_result=None,
            gpa=3.5,
            test_answers={},
            test_result="B"
        )
        dummy_pdf = SimpleUploadedFile("dummy.pdf", b"dummy content", content_type="application/pdf")
        ApplicationEvidence.objects.create(
            application=application,
            evidence_type=self.orphan_et,
            file=dummy_pdf
        )
        score = calculate_application_score(application)

        expected = 17.5 + 3
        self.assertEqual(score, expected)

    def test_serializer_create_and_score(self):
        """
        Проверяем работу сериализатора при создании заявки с вложенными доказательствами.
        """
        data = {
            "student": self.student1.id,
            "dormitory_cost": 1200,
            "test_answers": {},
            "test_result": "B",
            "ent_result": None,
            "gpa": 3.8,
            "evidences": [
                {
                    "evidence_type": "orphan_certificate",
                    "file": SimpleUploadedFile("dummy.pdf", b"dummy content", content_type="application/pdf")
                }
            ]
        }
        serializer = ApplicationSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)
        application = serializer.save()

        self.assertEqual(application.evidences.count(), 1)

        expected = self.gpa_et.priority * 3.8 + self.orphan_et.priority
        self.assertEqual(calculate_application_score(application), expected)
