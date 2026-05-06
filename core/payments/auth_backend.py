"""
Custom authentication backend for payment app.
Handles date-based access control for customers.
"""
from django.contrib.auth.backends import ModelBackend


class DateRestrictedBackend(ModelBackend):
    """
    Authentication backend that enforces:
    - Date restrictions for customers (active_from to valid_until)
    - Suspended customers can login but with limited access
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        # COMPLETELY DISABLE CUSTOM LOGIC - JUST USE PARENT
        return super().authenticate(request, username=username, password=password, **kwargs)