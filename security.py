import re
from functools import wraps
from typing import Callable, Any
import database as db


class SecurityManager:
    """Security features for the bot."""
    
    # Rate limits per action (limit, window_seconds)
    RATE_LIMITS = {
        "buy": (5, 300),        # 5 buys per 5 minutes
        "topup": (3, 3600),     # 3 topups per hour
        "balance_check": (20, 60),  # 20 checks per minute
        "categories": (30, 60),     # 30 per minute
        "products": (30, 60),       # 30 per minute
    }
    
    # Suspicious patterns
    SPAM_PATTERNS = [
        r"(.)\1{5,}",  # Repeated characters
        r"https?://\S+",  # URLs (potential phishing)
    ]
    
    @staticmethod
    def check_rate_limit(user_id: int, action: str) -> tuple[bool, str]:
        """Check if action is within rate limit."""
        limit, window = SecurityManager.RATE_LIMITS.get(action, (10, 60))
        allowed = db.check_rate_limit(user_id, action, limit, window)
        
        if not allowed:
            return False, f"Rate limit exceeded. Try again in {window} seconds."
        return True, ""
    
    @staticmethod
    def validate_quantity(quantity: int) -> tuple[bool, str]:
        """Validate purchase quantity."""
        if not isinstance(quantity, int):
            return False, "Quantity must be a whole number."
        if quantity < 1:
            return False, "Quantity must be at least 1."
        if quantity > 50:
            return False, "Maximum quantity is 50 per order."
        return True, ""
    
    @staticmethod
    def validate_amount(amount: float) -> tuple[bool, str]:
        """Validate topup amount."""
        if not isinstance(amount, (int, float)):
            return False, "Amount must be a number."
        if amount < 1:
            return False, "Minimum topup is $1."
        if amount > 10000:
            return False, "Maximum topup is $10,000."
        return True, ""
    
    @staticmethod
    def is_suspicious(text: str) -> bool:
        """Check if text contains suspicious content."""
        for pattern in SecurityManager.SPAM_PATTERNS:
            if re.search(pattern, text, re.IGNORECASE):
                return True
        return False
    
    @staticmethod
    def sanitize_input(text: str, max_length: int = 500) -> str:
        """Sanitize user input."""
        if not text:
            return ""
        # Remove control characters
        text = re.sub(r'[\x00-\x1f\x7f-\x9f]', '', text)
        # Truncate
        return text[:max_length].strip()
    
    @staticmethod
    def check_user_status(user_id: int) -> tuple[bool, str]:
        """Check if user is allowed to perform actions."""
        user = db.get_user(user_id)
        if not user:
            return False, "Please /start the bot first."
        if user.get("is_banned"):
            return False, "Your account has been suspended. Contact support."
        return True, ""
    
    @staticmethod
    def log_security_event(user_id: int, event: str, details: str = ""):
        """Log security events."""
        # In production, you'd log to a file or monitoring service
        print(f"[SECURITY] User {user_id}: {event} - {details}")


def require_auth(func: Callable) -> Callable:
    """Decorator to require user authentication."""
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        
        # Create user if not exists
        user = db.get_user(user_id)
        if not user:
            db.create_user(
                user_id,
                update.effective_user.username,
                update.effective_user.first_name
            )
        
        # Check if banned
        allowed, message = SecurityManager.check_user_status(user_id)
        if not allowed:
            await update.message.reply_text(f"❌ {message}")
            return
        
        # Update activity
        db.update_user_activity(user_id)
        
        return await func(update, context, *args, **kwargs)
    return wrapper


def require_admin(func: Callable) -> Callable:
    """Decorator to require admin privileges."""
    @wraps(func)
    async def wrapper(update, context, *args, **kwargs):
        user_id = update.effective_user.id
        admin_id = int(context.bot_data.get("admin_id", 0))
        
        if user_id != admin_id:
            await update.message.reply_text("⛔ Access denied. Admin only.")
            SecurityManager.log_security_event(user_id, "unauthorized_admin_access")
            return
        
        return await func(update, context, *args, **kwargs)
    return wrapper


security = SecurityManager()
