# bot.py - Message Point Tracker for @MyCAEVC_bot
import logging
import schedule
import time
import threading
from datetime import datetime, timedelta
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes
from config import BOT_TOKEN, CHAT_ID, TARGET_BOT_USERNAME, EXPECTED_MESSAGES, MESSAGE_PATTERNS

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
        """Get current hour as tracking key"""
        return datetime.now().strftime('%Y-%m-%d-%H')
    
    def get_hour_display(self, hour_key):
        """Convert hour key to display format"""
        dt = datetime.strptime(hour_key, '%Y-%m-%d-%H')
        return dt.strftime('%H:00-%H:59')
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle incoming messages and track specific points from target bot"""
        # Only process messages from the target group
        if update.effective_chat.id != CHAT_ID:
            return
            
        # Only process messages from @MyCAEVC_bot
        if (update.message.from_user and 
            update.message.from_user.username == TARGET_BOT_USERNAME):
            
            message_text = update.message.text
            point_type = self.identify_message_point(message_text)
            
            if point_type:
                hour_key = self.get_current_hour_key()
                
                # Initialize hour tracker if needed
                if hour_key not in self.hourly_tracker:
                    self.hourly_tracker[hour_key] = set()
                
                # Add point to tracker
                self.hourly_tracker[hour_key].add(point_type)
                
                logger.info(f"{point_type} from @{TARGET_BOT_USERNAME} logged for hour {hour_key}")
                
                # No real-time notifications - just log silently
    
    async def send_hourly_summary(self):
        """Send hourly summary at 59:15"""
        current_time = datetime.now()
        hour_key = current_time.strftime('%Y-%m-%d-%H')
        
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
        
        summary = f"""{status_emoji} Hour {hour_display} Summary:

Messages from @{TARGET_BOT_USERNAME}:
Received: {', '.join(sorted(received)) if received else 'None'} ({len(received)}/4)
Missing: {', '.join(sorted(missing)) if missing else 'None'}

Status: {status}
Time: {current_time.strftime('%H:%M:%S')}
        """
        
        # Send to group
        await self.application.bot.send_message(
            chat_id=CHAT_ID,
            text=summary
        )
        
        logger.info(f"Sent summary for hour {hour_key}: {len(received)}/{len(EXPECTED_MESSAGES)} points ({list(received)})")
        
        # Optional: Clear old data to save memory (keep last 24 hours)
        self.cleanup_old_data()
    
    def cleanup_old_data(self):
        """Remove data older than 24 hours"""
        current_time = datetime.now()
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
        logger.info("Scheduler started - summaries at 59:15 of each hour")
    
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
        hour_key = self.get_current_hour_key()
        received = self.hourly_tracker.get(hour_key, set())
        missing = set(EXPECTED_MESSAGES) - received
        
        current_time = datetime.now()
        minutes_left = 59 - current_time.minute
        
        status_msg = f"""Current Hour Status:

Time: {current_time.strftime('%H:%M:%S')} ({minutes_left} min left)
From @{TARGET_BOT_USERNAME}: {len(received)}/4

Received: {', '.join(sorted(received)) if received else 'None'}
Waiting for: {', '.join(sorted(missing)) if missing else 'All complete!'}
        """
        
        await update.message.reply_text(status_msg)
    
    def run_bot(self):
        """Start the bot"""
        # Create application
        self.application = Application.builder().token(BOT_TOKEN).build()
        
        # Add handlers - only message handler for tracking
        self.application.add_handler(MessageHandler(filters.TEXT, self.handle_message))
        
        # Optional: Keep status command for manual checking
        self.application.add_handler(CommandHandler("status", self.status_command))
        
        # Start scheduler for hourly summaries
        self.schedule_summaries()
        
        logger.info(f"Bot starting... Monitoring @{TARGET_BOT_USERNAME} for hourly summaries at 59:15")
        
        # Run bot
        self.application.run_polling(allowed_updates=Update.ALL_TYPES)

if __name__ == "__main__":
    tracker = MessagePointTracker()
    tracker.run_bot()
