# bot.py - Message Point Tracker for @MyCAEVC_bot
import logging
import schedule
import time
import threading
from datetime import datetime, timedelta
import pytz
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from config import BOT_TOKEN, CHAT_ID, TARGET_BOT_USERNAME, EXPECTED_MESSAGES, MESSAGE_PATTERNS

# Set timezone to Malaysia
MALAYSIA_TZ = pytz.timezone('Asia/Kuala_Lumpur')

# Set up logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

class MessagePointTracker:
    def __init__(self):
        self.hourly_tracker = {}  # {hour_key: set of received points (P1,P2,P3,P4)}
        self.application = None
        
    def identify_message_point(self, text):
        """Identify if message contains P1, P2, P3, or P4"""
        if not text:
            return None
            
        text_lower = text.lower()
        
        for point_type, patterns in MESSAGE_PATTERNS.items():
            for pattern in patterns:
                if pattern.lower() in text_lower:
                    return point_type
        return None
        
    def get_current_hour_key(self):
        """Get current hour as tracking key (use UTC for consistency)"""
        return datetime.utcnow().strftime('%Y-%m-%d-%H')
    
    def get_hour_display(self, hour_key):
        """Convert hour key to display format in Malaysia time"""
        dt_utc = datetime.strptime(hour_key, '%Y-%m-%d-%H')
        dt_utc = pytz.utc.localize(dt_utc)
        dt_malaysia = dt_utc.astimezone(MALAYSIA_TZ)
        return dt_malaysia.strftime('%H:00-%H:59')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages and track specific points from target bot"""
        try:
            # Debug logging - show ALL message details
            sender_username = update.message.from_user.username if update.message.from_user else 'None'
            sender_first_name = update.message.from_user.first_name if update.message.from_user else 'None'
            message_text = update.message.text[:100] if update.message.text else 'No text'
            
            logger.info(f"📨 MESSAGE RECEIVED:")
            logger.info(f"  Chat ID: {update.effective_chat.id}")
            logger.info(f"  Sender username: @{sender_username}")
            logger.info(f"  Sender first_name: {sender_first_name}")
            logger.info(f"  Message text: {message_text}")
            logger.info(f"  Looking for: @{TARGET_BOT_USERNAME}")
            logger.info(f"  Expected chat: {CHAT_ID}")
            
            # Only process messages from the target group
            if update.effective_chat.id != CHAT_ID:
                logger.info(f"❌ Wrong chat - ignoring")
                return
                
            # Check if sender matches target bot
            if (update.message.from_user and 
                update.message.from_user.username == TARGET_BOT_USERNAME):
                
                logger.info(f"✅ Message from target bot @{TARGET_BOT_USERNAME} detected!")
                point_type = self.identify_message_point(message_text)
                logger.info(f"🔍 Point detection result: {point_type}")
                
                if point_type:
                    hour_key = self.get_current_hour_key()
                    
                    # Initialize hour tracker if needed
                    if hour_key not in self.hourly_tracker:
                        self.hourly_tracker[hour_key] = set()
                    
                    # Add point to tracker
                    self.hourly_tracker[hour_key].add(point_type)
                    
                    logger.info(f"🎯 SUCCESS: {point_type} logged for hour {hour_key}")
                    logger.info(f"📊 Current hour data: {list(self.hourly_tracker[hour_key])}")
                else:
                    logger.info(f"❌ No P1/P2/P3/P4 pattern found in message")
            else:
                logger.info(f"❌ Sender @{sender_username} ≠ target @{TARGET_BOT_USERNAME} - ignoring")
                
        except Exception as e:
            logger.error(f"🚨 ERROR in handle_message: {e}")
            logger.error(f"🚨 Update object: {update}")
            import traceback
            logger.error(f"🚨 Traceback: {traceback.format_exc()}")
    
    async def send_hourly_summary(self):
        """Send hourly summary at 59:15"""
        current_time_utc = datetime.utcnow()
        current_time_malaysia = datetime.now(MALAYSIA_TZ)
        hour_key = current_time_utc.strftime('%Y-%m-%d-%H')
        
        # Get received points for this hour
        received = self.hourly_tracker.get(hour_key, set())
        missing = set(EXPECTED_MESSAGES) - received
        
        # Create summary message
        hour_display = self.get_hour_display(hour_key)
        
        # Status emoji
        if len(received) == len(EXPECTED_MESSAGES):
            status = "✅ COMPLETE"
            status_emoji = "🟢"
        elif len(received) > 0:
            status = "⚠️ INCOMPLETE" 
            status_emoji = "🟡"
        else:
            status = "❌ NO MESSAGES"
            status_emoji = "🔴"
        
        # Escape underscore in bot username for Markdown
        bot_name_escaped = TARGET_BOT_USERNAME.replace('_', '\\_')
        
        summary = f"""{status_emoji} *Hour {hour_display} Summary:*

📊 *Messages from @{bot_name_escaped}:*
✅ *Received:* {', '.join(sorted(received)) if received else 'None'} ({len(received)}/4)
❌ *Missing:* {', '.join(sorted(missing)) if missing else 'None'}

*Status:* {status}
*Time:* {current_time_malaysia.strftime('%H:%M:%S')} MYT
        """
        
        # Send to group
        await self.application.bot.send_message(
            chat_id=CHAT_ID,
            text=summary,
            parse_mode='Markdown'
        )
        
        logger.info(f"Sent summary for hour {hour_key}: {len(received)}/{len(EXPECTED_MESSAGES)} points ({list(received)})")
        
        # Optional: Clear old data to save memory (keep last 24 hours)
        self.cleanup_old_data()
    
    def cleanup_old_data(self):
        """Remove data older than 24 hours"""
        current_time = datetime.utcnow()
        cutoff_time = current_time - timedelta(hours=24)
        cutoff_key = cutoff_time.strftime('%Y-%m-%d-%H')
        
        keys_to_remove = [key for key in self.hourly_tracker.keys() if key < cutoff_key]
        for key in keys_to_remove:
            del self.hourly_tracker[key]
    
    def schedule_summaries(self):
        """Schedule the 59:15 summaries"""
        schedule.every().hour.at("59:15").do(self.run_summary)
        
        def scheduler_thread():
            while True:
                schedule.run_pending()
                time.sleep(30)  # Check every 30 seconds
        
        # Run scheduler in separate thread
        threading.Thread(target=scheduler_thread, daemon=True).start()
        logger.info("Scheduler started - summaries at 59:15 UTC (07:59:15 MYT)")
    
    def run_summary(self):
        """Wrapper to run async summary in sync context"""
        import asyncio
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self.send_hourly_summary())
        except Exception as e:
            logger.error(f"Error in summary: {e}")
    
    async def status_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle /status command for current hour progress (optional manual check)"""
        logger.info(f"Status command received from chat {update.effective_chat.id}, user: {update.message.from_user.username if update.message.from_user else 'None'}")
        logger.info(f"CHAT_ID configured: {CHAT_ID} (type: {type(CHAT_ID)})")
        
        # Check if command is from correct chat
        if update.effective_chat.id != CHAT_ID:
            logger.info(f"Status command from wrong chat. Expected: {CHAT_ID}, Got: {update.effective_chat.id}")
            return
        
        hour_key = self.get_current_hour_key()  # This uses UTC
        received = self.hourly_tracker.get(hour_key, set())
        missing = set(EXPECTED_MESSAGES) - received
        
        current_time_malaysia = datetime.now(MALAYSIA_TZ)
        minutes_left = 59 - current_time_malaysia.minute
        
        # Escape underscore in bot username for Markdown
        bot_name_escaped = TARGET_BOT_USERNAME.replace('_', '\\_')
        
        status_msg = f"""📊 *Current Hour Status:*

🕐 *Time:* {current_time_malaysia.strftime('%H:%M:%S')} MYT ({minutes_left} min left)
📨 *From @{bot_name_escaped}:* {len(received)}/4

✅ *Received:* {', '.join(sorted(received)) if received else 'None'}
⏳ *Waiting for:* {', '.join(sorted(missing)) if missing else 'All complete!'}

*Debug:* Tracking hour {hour_key} UTC
        """
        
        try:
            await update.message.reply_text(status_msg, parse_mode='Markdown')
            logger.info("Status response sent successfully")
        except Exception as e:
            logger.error(f"Error sending status response: {e}")
            # Try without markdown as fallback
            simple_msg = f"Current Hour Status:\nTime: {current_time_malaysia.strftime('%H:%M:%S')} MYT ({minutes_left} min left)\nFrom @{TARGET_BOT_USERNAME}: {len(received)}/4\nReceived: {', '.join(sorted(received)) if received else 'None'}\nWaiting for: {', '.join(sorted(missing)) if missing else 'All complete!'}\nDebug: Tracking hour {hour_key} UTC"
            await update.message.reply_text(simple_msg)
    
    def run_bot(self):
        """Start the bot"""
        # Create application
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        # IMPORTANT: Add CommandHandler BEFORE MessageHandler
        # Commands should be processed before general messages
        self.application.add_handler(CommandHandler("status", self.status_command))
        
        # Add message handler for tracking (only processes non-command messages)
        self.application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message))
        
        # Start scheduler for hourly summaries
        self.schedule_summaries()
        
        logger.info(f"Bot starting... Monitoring @{TARGET_BOT_USERNAME} for hourly summaries")
        logger.info(f"Summaries at 59:15 UTC (07:59:15 MYT)")
        logger.info(f"Configured CHAT_ID: {CHAT_ID} (type: {type(CHAT_ID)})")
        logger.info(f"Bot token: {BOT_TOKEN[:20]}...")
        
        # Start simple web server for Render (background thread)
        self.start_health_server()
        
        # Run bot
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)
    
    def start_health_server(self):
        """Start a simple health check server for Render"""
        import os
        from http.server import HTTPServer, BaseHTTPRequestHandler
        
        class HealthHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                self.send_response(200)
                self.send_header('Content-type', 'text/html')
                self.end_headers()
                self.wfile.write(b'Bot is running!')
            
            def log_message(self, format, *args):
                # Suppress HTTP server logs
                pass
        
        def run_server():
            port = int(os.environ.get('PORT', 10000))
            httpd = HTTPServer(('', port), HealthHandler)
            logger.info(f"Health server started on port {port}")
            httpd.serve_forever()
        
        # Run server in background thread
        threading.Thread(target=run_server, daemon=True).start()

if __name__ == "__main__":
    tracker = MessagePointTracker()
    tracker.run_bot()
