#!/usr/bin/env python
import os
import sys

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')
sys.path.insert(0, os.path.dirname(__file__))

import django
django.setup()

from django.core.management import call_command
from django.db import connection

# Check current migration status
cursor = connection.cursor()
cursor.execute("SELECT name FROM django_migrations WHERE app='payments' ORDER BY id DESC LIMIT 5")
migrations = cursor.fetchall()
print("Recent payments migrations:", migrations)

# Run migration
try:
    print("Running migration...")
    call_command('migrate', 'payments', '0030', verbosity=2)
    print("Migration completed!")
except Exception as e:
    print("Migration failed:", e)