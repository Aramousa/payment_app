import os
import sys
import django

# Add the project directory to the Python path
sys.path.insert(0, os.path.dirname(__file__))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# Setup Django
django.setup()

from django.contrib.auth import authenticate
from django.contrib.auth.models import User

print('Testing authentication...')

# Test admin login
admin_user = authenticate(username='admin', password='admin123')
print(f'Admin login result: {admin_user}')

# Test customer1 login
customer_user = authenticate(username='مشتری1', password='temp_password')
print(f'Customer1 login result: {customer_user}')

# Check all users
users = User.objects.all()
print(f'\nAll users ({users.count()}):')
for user in users:
    print(f'  {user.username}: active={user.is_active}, staff={user.is_staff}, superuser={user.is_superuser}')