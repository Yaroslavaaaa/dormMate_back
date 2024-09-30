from rest_framework import serializers
from .models import *

class StudentSerializer(serializers.ModelSerializer):
    class Meta:
        model = Student
        fields = ("first_name", "last_name")



class DormSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dorm
        fields = ("name", "cost")