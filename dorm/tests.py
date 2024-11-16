from django.test import TestCase
from .models import (
    Region, User, Student, Admin, Dorm, TestQuestion,
    Application, QuestionAnswer, StudentInDorm
)
from datetime import date


class RegionModelTest(TestCase):
    def test_create_region(self):
        region = Region.objects.create(region_name="Алматы")
        self.assertEqual(region.region_name, "Алматы")
        self.assertEqual(str(region), "Алматы")


class UserModelTest(TestCase):
    def test_create_user(self):
        user = User.objects.create_user(s="U12345678", password="testpassword")
        self.assertTrue(user.check_password("testpassword"))
        self.assertEqual(user.s, "U12345678")
        self.assertTrue(user.is_active)

    def test_create_superuser(self):
        admin = User.objects.create_superuser(s="F12345678", password="adminpassword")
        self.assertTrue(admin.is_staff)
        self.assertTrue(admin.is_superuser)


class StudentModelTest(TestCase):
    def test_create_student(self):
        region = Region.objects.create(region_name="Астана")
        student = Student.objects.create(
            s="S12345678",
            first_name="Иван",
            last_name="Иванов",
            region=region,
            course="1 курс",
        )
        self.assertEqual(student.s, "S12345678")
        self.assertEqual(student.first_name, "Иван")
        self.assertEqual(student.region.region_name, "Астана")


class AdminModelTest(TestCase):
    def test_create_admin(self):
        admin = Admin.objects.create(
            s="F12345678",
            first_name="Админ",
            department="Кафедра ИТ"
        )
        self.assertEqual(admin.s, "F12345678")
        self.assertEqual(admin.department, "Кафедра ИТ")


class DormModelTest(TestCase):
    def test_create_dorm(self):
        dorm = Dorm.objects.create(
            name="Общежитие №1",
            total_places=100,
            rooms_for_two=30,
            rooms_for_three=20,
            rooms_for_four=10,
            cost=20000
        )
        self.assertEqual(dorm.name, "Общежитие №1")
        self.assertEqual(dorm.total_places, 100)


class TestQuestionModelTest(TestCase):
    def test_create_question(self):
        question = TestQuestion.objects.create(
            question_text="Какой ваш режим дня?",
            answer_variant_a="Ранний подъем",
            answer_variant_b="Поздний подъем",
            answer_variant_c="Нет режима",
            question_type="daily_routine"
        )
        self.assertEqual(question.question_text, "Какой ваш режим дня?")


class ApplicationModelTest(TestCase):
    def test_create_application(self):
        region = Region.objects.create(region_name="Алматы")
        student = Student.objects.create(
            s="S12345678",
            first_name="Иван",
            last_name="Иванов",
            region=region,
            course="1 курс"
        )
        dorm = Dorm.objects.create(
            name="Общежитие №1",
            total_places=100,
            rooms_for_two=30,
            rooms_for_three=20,
            rooms_for_four=10,
            cost=20000
        )
        application = Application.objects.create(
            student=student,
            dormitory_choice=dorm,
            test_answers={"question1": "a", "question2": "b"},
            ent_result=95,
            gpa=3.5
        )
        self.assertEqual(application.student, student)
        self.assertEqual(application.dormitory_choice, dorm)


class QuestionAnswerModelTest(TestCase):
    def test_create_question_answer(self):
        answer = QuestionAnswer.objects.create(
            question="Ваш режим дня?",
            answer="Ранний подъем"
        )
        self.assertEqual(answer.question, "Ваш режим дня?")


class StudentInDormModelTest(TestCase):
    def test_create_student_in_dorm(self):
        region = Region.objects.create(region_name="Алматы")
        student = Student.objects.create(
            s="S12345678",
            first_name="Иван",
            last_name="Иванов",
            region=region,
            course="1 курс"
        )
        dorm = Dorm.objects.create(
            name="Общежитие №1",
            total_places=100,
            rooms_for_two=30,
            rooms_for_three=20,
            rooms_for_four=10,
            cost=20000
        )
        application = Application.objects.create(
            student=student,
            dormitory_choice=dorm,
            test_answers={"question1": "a"},
            ent_result=95,
            gpa=3.5
        )
        student_in_dorm = StudentInDorm.objects.create(
            student_id=student,
            dorm_id=dorm,
            room="101",
            application_id=application
        )
        self.assertEqual(student_in_dorm.student_id, student)
        self.assertEqual(student_in_dorm.dorm_id, dorm)
        self.assertEqual(student_in_dorm.room, "101")
