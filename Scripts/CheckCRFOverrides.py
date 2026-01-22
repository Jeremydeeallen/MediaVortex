#!/usr/bin/env python3
"""Check CRF overrides in the database."""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from Repositories.DatabaseManager import DatabaseManager

db = DatabaseManager()
settings = db.DatabaseService.ExecuteQuery("SELECT SettingKey, SettingValue, Description FROM SystemSettings WHERE SettingKey LIKE 'CRFOverride_%'")

print("CRF Overrides in database:")
print("-" * 80)
if settings:
    for s in settings:
        print(f"Key: {s['SettingKey']}")
        print(f"Value: {s['SettingValue']}")
        print(f"Description: {s['Description']}")
        print("-" * 80)
else:
    print("No CRF overrides found in database.")

