import os, sys, django
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
from django.contrib.auth import authenticate

users = User.objects.all()
print('Users in database:')
for user in users:
    print(f'  {user.username}: active={user.is_active}, staff={user.is_staff}, superuser={user.is_superuser}')
    # Test authentication with a common password
    result = authenticate(username=user.username, password='123456')
    print(f'    Auth test with 123456: {result is not None}')
    if user.username == 'مشتری1':
        result2 = authenticate(username=user.username, password='temp_password')
        print(f'    Auth test with temp_password: {result2 is not None}')