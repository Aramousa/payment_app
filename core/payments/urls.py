from django.urls import path
from .views import create_payment, success

urlpatterns = [
    path('submit/', create_payment, name='submit'),
    path('success/', success, name='success'),
]
