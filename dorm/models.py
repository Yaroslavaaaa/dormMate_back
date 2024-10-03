from django.db import models



class Region(models.Model):
    region_name = models.CharField(max_length=100, verbose_name="Область")


    def __str__(self):
        return f"{self.region_name}"

class Student(models.Model):
    student_s = models.CharField(max_length=100, verbose_name="S-ка студента")
    first_name = models.CharField(max_length=100, verbose_name="Имя")
    last_name = models.CharField(max_length=100, verbose_name="Фамилия")
    middle_name = models.CharField(max_length=100, verbose_name="Отчество", blank=True, null=True)
    region = models.ForeignKey(Region, on_delete=models.CASCADE, verbose_name="Область")
    course = models.PositiveIntegerField(verbose_name="Курс")
    email = models.EmailField(verbose_name="Почта")

    def __str__(self):
        return f"{self.last_name} {self.first_name} ({self.student_s})"






class Dorm(models.Model):
    name = models.CharField(max_length=255, verbose_name="Название")
    total_places = models.PositiveIntegerField(verbose_name="Количество мест")
    rooms_for_two = models.PositiveIntegerField(verbose_name="Количество комнат на 2")
    rooms_for_three = models.PositiveIntegerField(verbose_name="Количество комнат на 3")
    rooms_for_four = models.PositiveIntegerField(verbose_name="Количество комнат на 4")
    cost = models.PositiveIntegerField(verbose_name="Стоимость")

    def __str__(self):
        return self.name


# class Application(models.Model):
#     student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name="Студент", related_name="applications")
#     approval = models.BooleanField(default=False, verbose_name="Одобрение")
#     dormitory_choice = models.ForeignKey(Dorm, on_delete=models.SET_NULL, null=True, default=None, verbose_name="Выбор по цене")
#     test_result = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=None, verbose_name="Результат теста")
#
#     def __str__(self):
#         return f"Заявка от {self.student}"

class TestQuestion(models.Model):
    QUESTION_TYPE_CHOICES = [
        ('psychological', 'Психологическая совместимость'),
        ('daily_routine', 'Режим дня'),
        ('habits', 'Вредные привычки'),
        ('values', 'Ценности'),
        ('household', 'Бытовые привычки'),
    ]

    question_text = models.TextField(verbose_name="Вопрос")
    question_type = models.CharField(max_length=50, choices=QUESTION_TYPE_CHOICES, verbose_name="Тип вопроса")

    def __str__(self):
        return self.question_text

class TestAnswer(models.Model):
    question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE, related_name='answers', verbose_name="Вопрос")
    answer_text = models.CharField(max_length=255, verbose_name="Ответ")
    score = models.IntegerField(verbose_name="Баллы")

    def __str__(self):
        return f"{self.answer_text} ({self.score} баллов)"

class Application(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, verbose_name="Студент", related_name="applications")
    approval = models.BooleanField(default=False, verbose_name="Одобрение")
    dormitory_choice = models.ForeignKey(Dorm, on_delete=models.SET_NULL, null=True, default=None, verbose_name="Выбор общежития")
    test_result = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True, default=None, verbose_name="Результат теста")

    def __str__(self):
        return f"Заявка от {self.student}"

class TestResult(models.Model):
    application = models.ForeignKey(Application, on_delete=models.CASCADE, verbose_name="Заявка", related_name="test_results")
    question = models.ForeignKey(TestQuestion, on_delete=models.CASCADE, verbose_name="Вопрос")
    selected_answer = models.ForeignKey(TestAnswer, on_delete=models.CASCADE, verbose_name="Выбранный ответ")

    def __str__(self):
        return f"{self.application.student} - {self.question} ({self.selected_answer})"