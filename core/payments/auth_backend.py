"""
Custom authentication backend for payment app.
Handles date-based access control for customers.
"""
import jdatetime
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth.models import User
from .models import UserProfile


class DateRestrictedBackend(ModelBackend):
    """
    Authentication backend that enforces:
    - Date restrictions for customers (active_from to valid_until)
    - Suspended customers can login but with limited access
    """

    def authenticate(self, request, username=None, password=None, **kwargs):
        if not username:
            return None

        try:
            user = User.objects.get(username=username)
        except User.DoesNotExist:
            return None

        if not user.is_active:
            return None

        # Check if user has a profile
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            # No profile - allow login (likely admin or staff without profile)
            return user

        # For customers, check date restrictions
        if profile.role == 'customer':
            today = jdatetime.date.today()

            # Check if customer is suspended - allow login but limited access
            if profile.suspended:
                # Suspended customers can login but will have limited access
                return user

            # Check date restrictions for non-suspended customers
            if profile.active_from and profile.valid_until:
                if today < profile.active_from or today > profile.valid_until:
                    # Outside valid date range - deny login
                    return None

            # If only active_from is set and today is before it
            if profile.active_from and not profile.valid_until:
                if today < profile.active_from:
                    return None

            # If only valid_until is set and today is after it
            if profile.valid_until and not profile.active_from:
                if today > profile.valid_until:
                    return None

        # Finance and commercial users have no date restrictions
        return user

    def user_can_authenticate(self, user):
        """
        Reject users that are not allowed to authenticate.
        """
        if not user.is_active:
            return False

        # Check profile for additional restrictions
        try:
            profile = user.profile
        except UserProfile.DoesNotExist:
            return True

        # For customers, apply date restrictions
        if profile.role == 'customer':
            today = jdatetime.date.today()

            # Suspended customers can authenticate
            if profile.suspended:
                return True

            # Check date range
            if profile.active_from and profile.valid_until:
                if today < profile.active_from or today > profile.valid_until:
                    return False

            if profile.active_from and not profile.valid_until:
                if today < profile.active_from:
                    return False

            if profile.valid_until and not profile.active_from:
                if today > profile.valid_until:
                    return False

        return True