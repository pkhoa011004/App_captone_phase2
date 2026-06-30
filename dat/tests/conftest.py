import datetime
import sys

# Patch datetime.UTC for compatibility with Python < 3.11
if not hasattr(datetime, "UTC"):
    datetime.UTC = datetime.timezone.utc
    sys.modules["datetime"].UTC = datetime.timezone.utc
