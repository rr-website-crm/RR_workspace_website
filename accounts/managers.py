from django.contrib.auth.models import UserManager
from django.utils import timezone

class CustomUserManager(UserManager):

    def create_superuser(self, email, password, **extra_fields):
        extra_fields.setdefault('role', 'superadmin')
        extra_fields.setdefault('is_staff', True)
        extra_fields.setdefault('is_superuser', True)
        extra_fields.setdefault('is_active', True)
        extra_fields.setdefault('is_approved', True)
        extra_fields.setdefault('approval_status', 'approved')
        extra_fields.setdefault('approved_at', timezone.now())

        return super().create_superuser(email=email, password=password, **extra_fields)
