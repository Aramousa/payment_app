import os, sys, django
sys.path.insert(0, os.getcwd())
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
django.setup()

from django.contrib.auth.models import User
users = User.objects.all()
print('Users in database:')
for user in users:
    print(f'  {user.username}: active={user.is_active}, staff={user.is_staff}, superuser={user.is_superuser}')