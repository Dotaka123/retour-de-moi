from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes
import database as db
from security import require_admin, SecurityManager


@require_admin
async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Show admin panel."""
    keyboard = [
        [
            InlineKeyboardButton("👥 Users", callback_data="admin_users"),
            InlineKeyboardButton("📊 Stats", callback_data="admin_stats")
        ],
        [
            InlineKeyboardButton("💰 Topups", callback_data="admin_topups"),
            InlineKeyboardButton("📦 Orders", callback_data="admin_orders")
        ],
        [
            InlineKeyboardButton("💳 Set Balance", callback_data="admin_set_balance"),
            InlineKeyboardButton("🚫 Ban User", callback_data="admin_ban")
        ],
        [
            InlineKeyboardButton("📢 Broadcast", callback_data="admin_broadcast")
        ]
    ]
    
    await update.message.reply_text(
        "🔧 *Admin Panel*\n\n"
        "Welcome to the Kaonty Store admin panel.\n"
        "Select an option below:",
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def admin_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle admin callback queries."""
    query = update.callback_query
    await query.answer()
    
    data = query.data
    user_id = update.effective_user.id
    admin_id = int(context.bot_data.get("admin_id", 0))
    
    if user_id != admin_id:
        await query.edit_message_text("⛔ Access denied.")
        return
    
    if data == "admin_users":
        await show_users(query)
    elif data == "admin_stats":
        await show_stats(query)
    elif data == "admin_topups":
        await show_topups(query)
    elif data == "admin_orders":
        await show_orders(query)
    elif data.startswith("admin_approve_"):
        topup_id = int(data.split("_")[2])
        await approve_topup(query, topup_id, context)
    elif data.startswith("admin_reject_"):
        topup_id = int(data.split("_")[2])
        await reject_topup(query, topup_id, context)
    elif data.startswith("admin_unban_"):
        target_id = int(data.split("_")[2])
        await unban_user(query, target_id)
    elif data == "admin_broadcast":
        await query.edit_message_text(
            "📢 *Broadcast Message*\n\n"
            "Send me the message you want to broadcast to all users.\n"
            "Send /cancel to cancel.",
            parse_mode="Markdown"
        )
        context.user_data["awaiting_broadcast"] = True


async def show_users(query):
    """Show user list."""
    users = db.get_all_users()
    text = f"👥 *Users ({len(users)})*\n\n"
    
    for user in users[:20]:  # Show first 20
        status = "🚫" if user["is_banned"] else "✅"
        username = f"@{user['username']}" if user["username"] else user["first_name"]
        text += f"{status} `{user['telegram_id']}` - {username}\n"
        text += f"   💰 ${user['balance']:,.2f}\n\n"
    
    if len(users) > 20:
        text += f"\n... and {len(users) - 20} more users"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_stats(query):
    """Show bot statistics."""
    users = db.get_all_users()
    orders = db.get_all_orders()
    
    total_balance = sum(u["balance"] for u in users)
    total_spent = sum(o["total_cost"] for o in orders)
    
    text = (
        "📊 *Bot Statistics*\n\n"
        f"👥 Total Users: {len(users)}\n"
        f"📦 Total Orders: {len(orders)}\n"
        f"💰 Total User Balances: ${total_balance:,.2f}\n"
        f"💸 Total Revenue: ${total_spent:,.2f}\n"
    )
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_topups(query):
    """Show pending topups."""
    topups = db.get_pending_topups()
    
    if not topups:
        text = "💰 *Pending Topups*\n\nNo pending topup requests."
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
    
    text = "💰 *Pending Topups*\n\n"
    keyboard = []
    
    for t in topups[:10]:
        username = f"@{t['username']}" if t["username"] else t["first_name"]
        text += f"• {username} - ${t['amount']:,.2f}\n"
        if t.get("txid"):
            text += f"  TXID: {t['txid']}\n"
        if t.get("binance_id"):
            text += f"  Binance ID: {t['binance_id']}\n"
        
        keyboard.append([
            InlineKeyboardButton(f"✅ Approve ${t['amount']:,.0f}", callback_data=f"admin_approve_{t['id']}"),
            InlineKeyboardButton("❌ Reject", callback_data=f"admin_reject_{t['id']}")
        ])
    
    keyboard.append([InlineKeyboardButton("🔙 Back", callback_data="admin_back")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def approve_topup(query, topup_id, context):
    """Approve a topup request."""
    topup = db.approve_topup(topup_id)
    
    if topup:
        # Notify user
        try:
            await context.bot.send_message(
                chat_id=topup["user_id"],
                text=f"✅ *Topup Approved!*\n\n"
                     f"Your balance has been credited with ${topup['amount']:,.2f}\n"
                     f"Use /balance to check your new balance.",
                parse_mode="Markdown"
            )
        except Exception:
            pass
        
        await query.answer("✅ Topup approved!")
        await show_topups(query)
    else:
        await query.answer("❌ Failed to approve topup.")


async def reject_topup(query, topup_id, context=None):
    """Reject a topup request."""
    # Get topup info before rejecting
    topup_info = None
    try:
        import database as _db
        conn = _db.get_db()
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM {_db.T_TOPUPS} WHERE id = %s", (topup_id,))
            topup_info = cur.fetchone()
        conn.close()
    except Exception:
        pass

    if db.reject_topup(topup_id):
        # Notify user
        if context and topup_info:
            try:
                await context.bot.send_message(
                    chat_id=topup_info["user_id"],
                    text=f"❌ *Topup Rejected*\n\n"
                         f"Your topup request of ${topup_info['amount']:,.2f} has been rejected.\n"
                         f"Contact support if you believe this is an error.",
                    parse_mode="Markdown"
                )
            except Exception:
                pass
        await query.answer("❌ Topup rejected.")
        await show_topups(query)
    else:
        await query.answer("❌ Failed to reject topup.")


async def show_orders(query):
    """Show recent orders."""
    orders = db.get_all_orders()
    
    if not orders:
        text = "📦 *Recent Orders*\n\nNo orders yet."
        keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
        await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
    
    text = "📦 *Recent Orders*\n\n"
    for o in orders[:15]:
        text += f"• `{o['user_id']}` - {o['product_name']}\n"
        text += f"  Qty: {o['quantity']} | ${o['total_cost']:,.2f}\n\n"
    
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="admin_back")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def unban_user(query, target_id):
    """Unban a user."""
    if db.unban_user(target_id):
        await query.answer(f"✅ User {target_id} unbanned!")
    else:
        await query.answer("❌ Failed to unban user.")


async def handle_broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle broadcast message."""
    user_id = update.effective_user.id
    admin_id = int(context.bot_data.get("admin_id", 0))
    
    if user_id != admin_id:
        return
    
    if context.user_data.get("awaiting_broadcast"):
        message = update.message.text
        context.user_data["awaiting_broadcast"] = False
        
        if message == "/cancel":
            await update.message.reply_text("❌ Broadcast cancelled.")
            return
        
        users = db.get_all_users()
        sent = 0
        failed = 0
        
        for user in users:
            try:
                await context.bot.send_message(
                    chat_id=user["telegram_id"],
                    text=f"📢 *Kaonty Store*\n\n{message}",
                    parse_mode="Markdown"
                )
                sent += 1
            except Exception:
                failed += 1
        
        await update.message.reply_text(
            f"📢 *Broadcast Complete*\n\n"
            f"✅ Sent: {sent}\n"
            f"❌ Failed: {failed}",
            parse_mode="Markdown"
        )


async def handle_admin_set_balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Handle set balance command."""
    user_id = update.effective_user.id
    admin_id = int(context.bot_data.get("admin_id", 0))
    
    if user_id != admin_id:
        return
    
    if context.user_data.get("awaiting_set_balance"):
        try:
            parts = update.message.text.split()
            if len(parts) < 2:
                await update.message.reply_text("Usage: /setbalance <user_id> <amount>")
                return
            
            target_id = int(parts[0])
            amount = float(parts[1])
            
            if db.set_balance(target_id, amount):
                await update.message.reply_text(
                    f"✅ Balance set to ${amount:,.2f} for user `{target_id}`",
                    parse_mode="Markdown"
                )
            else:
                await update.message.reply_text("❌ Failed to set balance.")
        except ValueError:
            await update.message.reply_text("❌ Invalid format. Use: /setbalance <user_id> <amount>")
        
        context.user_data["awaiting_set_balance"] = False
