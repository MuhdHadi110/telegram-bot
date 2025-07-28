# config.py
import os

# Use environment variables for security
BOT_TOKEN = os.getenv('BOT_TOKEN', 'YOUR_BOT_TOKEN_HERE')
CHAT_ID = int(os.getenv('CHAT_ID', '-1002180864230'))

TARGET_BOT_USERNAME = "MyCAEVC_bot"
EXPECTED_MESSAGES = ['P1', 'P2', 'P3', 'P4']

MESSAGE_PATTERNS = {
    'P1': ['P1 '],
    'P2': ['P2 '], 
    'P3': ['P3 '],
    'P4': ['P4 ']
}
