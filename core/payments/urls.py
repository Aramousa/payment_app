from django.urls import path
from .views import (
    counterparty_edit,
    counterparties_manage,
    create_payment,
    edit_payment,
    export_records,
    payment_timeline,
    staff_update_status,
    success,
)

urlpatterns = [
    path('submit/', create_payment, name='submit'),
    path('success/', success, name='success'),
    path('payments/<int:payment_id>/status/', staff_update_status, name='staff_update_status'),
    path('payments/<int:payment_id>/edit/', edit_payment, name='edit_payment'),
    path('payments/<int:payment_id>/timeline/', payment_timeline, name='payment_timeline'),
    path('counterparties/', counterparties_manage, name='counterparties_manage'),
    path('counterparties/<int:counterparty_id>/edit/', counterparty_edit, name='counterparty_edit'),
    path('export-records/', export_records, name='export_records'),
]
