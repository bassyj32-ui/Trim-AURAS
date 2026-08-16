"""Update trimaura-secrets-v2 with correct GROQ_API_KEY."""
import subprocess
import sys
from app.config import settings

# Read the actual env file
groq_key = settings.groq_api_key
print(f"GROQ_API_KEY from env: {groq_key[:15]}...")

# Delete old secret first
subprocess.run(
    [sys.executable, "-m", "modal", "secret", "delete", "trimaura-secrets-v2", "-y"],
    check=False,
)

# Recreate with GROQ_API_KEY explicitly
result = subprocess.run(
    [
        sys.executable, "-m", "modal", "secret", "create", "trimaura-secrets-v2",
        f"GROQ_API_KEY={groq_key}",
        f"DEEPSEEK_API_KEY={settings.deepseek_api_key}",
        f"R2_ACCOUNT_ID={settings.r2_account_id}",
        f"R2_ACCESS_KEY_ID={settings.r2_access_key_id}",
        f"R2_SECRET_ACCESS_KEY={settings.r2_secret_access_key}",
        f"R2_BUCKET_NAME={settings.r2_bucket_name}",
        f"R2_PUBLIC_DOMAIN={settings.r2_public_domain}",
        f"SENTRY_DSN={settings.sentry_dsn}",
        f"VAPID_PUBLIC_KEY={settings.vapid_public_key}",
        f"VAPID_PRIVATE_KEY={settings.vapid_private_key}",
        f"VAPID_SUBJECT={settings.vapid_subject}",
        "APP_ENV=production",
    ],
    capture_output=True,
    text=True,
)
print(result.stdout)
if result.returncode != 0:
    print("STDERR:", result.stderr)
    sys.exit(1)

print("Secret updated successfully!")
