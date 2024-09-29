from rest_framework import generics
from django.shortcuts import render
from .models import *
from .serializers import *


# Create your views here.

class StudentAPIView(generics.ListAPIView):
    queryset = Student.objects.all()
    serializer_class = StudentSerializer