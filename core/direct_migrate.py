import subprocess
import sys
import os

# Change to project directory
os.chdir(os.path.dirname(__file__))

# Run manage.py migrate
result = subprocess.run([
    sys.executable, 'manage.py', 'migrate', 'payments'
], capture_output=True, text=True)

print("Return code:", result.returncode)
print("STDOUT:", result.stdout)
print("STDERR:", result.stderr)