from django.urls import path
from .views import create_payment, edit_payment, mark_incomplete, mark_reviewed, success

urlpatterns = [
    path('submit/', create_payment, name='submit'),
    path('success/', success, name='success'),
    path('payments/<int:payment_id>/mark-reviewed/', mark_reviewed, name='mark_reviewed'),
    path('payments/<int:payment_id>/mark-incomplete/', mark_incomplete, name='mark_incomplete'),
    path('payments/<int:payment_id>/edit/', edit_payment, name='edit_payment'),
]
