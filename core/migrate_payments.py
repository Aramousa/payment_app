#!/usr/bin/env python
import os
import sys

# Add current directory to path
sys.path.insert(0, os.path.dirname(__file__))

# Set environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'core.settings')

# Setup Django
import django
django.setup()

from django.core.management import call_command

# Run migration
try:
    call_command('migrate', 'payments', verbosity=2)
    print("Migration completed successfully!")
except Exception as e:
    print("Migration failed:", e)