import os
import time
import logging
import threading
import urllib.request
import json
from dotenv import load_dotenv
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application, CommandHandler, CallbackQueryHandler,
    MessageHandler, ContextTypes, filters
)

import database as db
from api_client import api_client
from security import security, require_auth, SecurityManager

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_ID = int(os.getenv("ADMIN_ID", 0))
BOT_NAME = os.getenv("BOT_NAME", "Kaonty Store")
BINANCE_EMAIL = os.getenv("BINANCE_EMAIL", "")

# Exchange rate: 1 USD = 1550 NGN
NGN_TO_USD = 1550.0

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)


def _s(*parts):
    return "".join(str(p) for p in parts)


def ngn_to_usd(ngn_price):
    """Convert NGN price from API to USD (bot price = API price / 2)."""
    return float(ngn_price) / NGN_TO_USD / 2


def fmt_usd(amount):
    """Format as USD string."""
    return "${:,.2f}".format(amount)


# ==================== Translations ====================

T = {
    "en": {
        "welcome": "\U0001f44b Welcome to *{}*!\n\nYour one-stop shop for premium logs.\n\n\U0001f539 Browse products\n\U0001f539 Purchase instantly\n\U0001f539 Secure & fast delivery\n\nUse the buttons below to get started!",
        "choose_lang": "\U0001f310 Choose your language / Choisissez votre langue:",
        "products": "\U0001f4e6 Products",
        "balance": "\U0001f4b0 Balance",
        "my_orders": "\U0001f4cb My Orders",
        "topup": "\U0001f4b3 Top Up",
        "help": "\u2753 Help",
        "back": "\U0001f519 Back",
        "categories_title": "\U0001f4c1 *Categories*\n\nSelect a category:",
        "loading": "\u23f3 Loading...",
        "error": "\u274c Error",
        "balance_title": "\U0001f4b0 *Your Balance*\n\nBalance: {}\n\nUse /topup to add funds.",
        "orders_empty": "\U0001f4cb *Your Orders*\n\nNo orders yet!",
        "orders_title": "\U0001f4cb *Your Orders*\n\n",
        "keys_purchased": "\U0001f511 {} key(s) purchased",
        "view_keys": "\U0001f441\ufe0f View Keys - ",
        "view_keys_title": "\U0001f511 *{}*\nQty: {} | {}\n\n",
        "key_label": "*Key {}*\n{}\n\n",
        "topup_title": "\U0001f4b3 *Top Up Your Account*\n\n*Step 1:* Send via *Binance Pay* to:\n`{}`\n\n*Step 2:* Enter the amount you sent (in USD)\nMinimum: $1\nMaximum: $10,000\n\nSend /cancel to cancel.",
        "topup_start": "\U0001f4b3 Top Up Now",
        "topup_info_title": "\U0001f4b3 *Top Up Instructions*\n\n1\ufe0f\u20e3 Send via *Binance Pay* to:\n`{}`\n\n2\ufe0f\u20e3 Use /topup and enter the amount\n\n3\ufe0f\u20e3 Wait for admin approval\n\n\U0001f4a1 Include your Telegram username!",
        "help_title": "\u2753 *{} Help*\n\n\U0001f4cc *How to buy:*\n1. Browse products\n2. Select quantity\n3. Confirm\n4. Receive keys!\n\n\U0001f4b3 *Top Up (via Binance Pay):*\nSend to: `{}`\nThen use /topup\n\n\U0001f6e1\ufe0f Contact admin for support.",
        "welcome_menu": "\U0001f44b *Welcome to {}*\n\nYour one-stop shop for premium logs.\n\nUse the buttons below:",
        "confirm_buy": "\U0001f522 *Select Quantity*\n\nHow many would you like to buy?",
        "confirm_title": "\U0001f6d2 *Confirm Purchase*\n\nProduct: {}\nQty: {}\nPrice: {}\n\nClick Confirm to proceed.",
        "confirm_btn": "\u2705 Confirm",
        "cancel_btn": "\u274c Cancel",
        "processing": "\u23f3 Processing your order...",
        "insufficient": "\u274c *Insufficient Balance*\n\nRequired: {}\nYour balance: {}\n\nUse /topup to add funds.",
        "purchase_ok": "\u2705 *Purchase Successful!*\n\n\U0001f4e6 Product: {}\n\U0001f522 Qty: {}\n\U0001f4b0 Cost: {}\n\n*Your Keys:*\n{}\n\u26a0\ufe0f Save these keys!",
        "topup_step2": "\U0001f4b3 *Step 2: Transaction ID (TXID)*\n\nEnter the Binance Transaction ID (TXID) from your payment.\n\nSend /cancel to cancel.",
        "topup_step3": "\U0001f4b3 *Step 3: Binance ID*\n\nEnter your Binance User ID.\n\nSend /cancel to cancel.",
        "topup_submitted": "\u2705 *Top Up Request Submitted*\n\nAmount: {}\nTXID: `{}`\nBinance ID: `{}`\n\nYour request is pending approval.",
        "admin_panel": "\U0001f527 *Admin Panel*\n\nAccess the web admin panel:\n\U0001f310 `http://localhost:5000`\n\n\U0001f510 Login with your admin password.",
        "access_denied": "\u26d4 Access denied.",
        "no_products": "No products available",
        "in_stock": "in stock",
        "select_qty": "\U0001f522 *Select Quantity*\n\nHow many would you like to buy?",
    },
    "fr": {
        "welcome": "\U0001f44b Bienvenue sur *{}* !\n\nVotre boutique pour les logs premium.\n\n\U0001f539 Parcourir les produits\n\U0001f539 Achat instantan\u00e9\n\U0001f539 Livraison s\u00e9curis\u00e9e\n\nUtilisez les boutons ci-dessous !",
        "choose_lang": "\U0001f310 Choisissez votre langue / Choose your language:",
        "products": "\U0001f4e6 Produits",
        "balance": "\U0001f4b0 Solde",
        "my_orders": "\U0001f4cb Mes Commandes",
        "topup": "\U0001f4b3 Recharger",
        "help": "\u2753 Aide",
        "back": "\U0001f519 Retour",
        "categories_title": "\U0001f4c1 *Cat\u00e9gories*\n\nS\u00e9lectionnez une cat\u00e9gorie :",
        "loading": "\u23f3 Chargement...",
        "error": "\u274c Erreur",
        "balance_title": "\U0001f4b0 *Votre Solde*\n\nSolde : {}\n\nUtilisez /topup pour ajouter des fonds.",
        "orders_empty": "\U0001f4cb *Vos Commandes*\n\nAucune commande pour le moment !",
        "orders_title": "\U0001f4cb *Vos Commandes*\n\n",
        "keys_purchased": "\U0001f511 {} cl\u00e9(s) achet\u00e9e(s)",
        "view_keys": "\U0001f441\ufe0f Voir les cl\u00e9s - ",
        "view_keys_title": "\U0001f511 *{}*\nQty : {} | {}\n\n",
        "key_label": "*Cl\u00e9 {}*\n{}\n\n",
        "topup_title": "\U0001f4b3 *Recharger Votre Compte*\n\n*\u00c9tape 1 :* Envoyez via *Binance Pay* \u00e0 :\n`{}`\n\n*\u00c9tape 2 :* Entrez le montant envoy\u00e9 (en USD)\nMinimum : $1\nMaximum : $10 000\n\nEnvoyez /cancel pour annuler.",
        "topup_start": "\U0001f4b3 Recharger",
        "topup_info_title": "\U0001f4b3 *Instructions de Rechargement*\n\n1\ufe0f\u20e3 Envoyez via *Binance Pay* \u00e0 :\n`{}`\n\n2\ufe0f\u20e3 Utilisez /topup et entrez le montant\n\n3\ufe0f\u20e3 Attendez l'approbation\n\n\U0001f4a1 Incluez votre nom d'utilisateur Telegram !",
        "help_title": "\u2753 *{} Aide*\n\n\U0001f4cc *Comment acheter :*\n1. Parcourir les produits\n2. Choisir la quantit\u00e9\n3. Confirmer\n4. Recevoir les cl\u00e9s !\n\n\U0001f4b3 *Rechargement (via Binance Pay) :*\nEnvoyez \u00e0 : `{}`\nPuis utilisez /topup\n\n\U0001f6e1\ufe0f Contactez l'admin pour le support.",
        "welcome_menu": "\U0001f44b *Bienvenue sur {}*\n\nVotre boutique pour les logs premium.\n\nUtilisez les boutons ci-dessous :",
        "confirm_buy": "\U0001f522 *Choisir la Quantit\u00e9*\n\nCombien souhaitez-vous acheter ?",
        "confirm_title": "\U0001f6d2 *Confirmer l'Achat*\n\nProduit : {}\nQt\u00e9 : {}\nPrix : {}\n\nCliquez sur Confirmer.",
        "confirm_btn": "\u2705 Confirmer",
        "cancel_btn": "\u274c Annuler",
        "processing": "\u23f3 Traitement de votre commande...",
        "insufficient": "\u274c *Solde Insuffisant*\n\nRequis : {}\nVotre solde : {}\n\nUtilisez /topup pour ajouter des fonds.",
        "purchase_ok": "\u2705 *Achat R\u00e9ussi !*\n\n\U0001f4e6 Produit : {}\n\U0001f522 Qt\u00e9 : {}\n\U0001f4b0 Co\u00fbt : {}\n\n*Vos Cl\u00e9s :*\n{}\n\u26a0\ufe0f Sauvegardez vos cl\u00e9s !",
        "topup_step2": "\U0001f4b3 *\u00c9tape 2 : ID de Transaction (TXID)*\n\nEntrez le TXID de votre paiement Binance.\n\nEnvoyez /cancel pour annuler.",
        "topup_step3": "\U0001f4b3 *\u00c9tape 3 : ID Binance*\n\nEntrez votre ID utilisateur Binance.\n\nEnvoyez /cancel pour annuler.",
        "topup_submitted": "\u2705 *Demande de Rechargement Soumise*\n\nMontant : {}\nTXID : `{}`\nID Binance : `{}`\n\nVotre demande est en attente d'approbation.",
        "admin_panel": "\U0001f527 *Panneau Admin*\n\nAcc\u00e9dez au panneau web :\n\U0001f310 `http://localhost:5000`\n\n\U0001f510 Connectez-vous avec votre mot de passe.",
        "access_denied": "\u26d4 Acc\u00e8s refus\u00e9.",
        "no_products": "Aucun produit disponible",
        "in_stock": "en stock",
        "select_qty": "\U0001f522 *Choisir la Quantit\u00e9*\n\nCombien souhaitez-vous acheter ?",
    }
}


def get_lang(user_id):
    """Get user language preference."""
    try:
        return db.get_language(user_id)
    except Exception:
        return "en"


def t(user_id, key, *args):
    """Get translated text."""
    lang = get_lang(user_id)
    text = T.get(lang, T["en"]).get(key, T["en"].get(key, key))
    if args:
        text = text.format(*args)
    return text


# ==================== User Commands ====================

@require_auth
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    db.create_user(user.id, user.username, user.first_name)

    # Check if user already has a language set
    lang = get_lang(user.id)
    if lang != "en":
        # Already has language, go to menu
        await show_main_menu(update, context, user.id)
        return

    # New user — ask language
    keyboard = [
        [InlineKeyboardButton("\U0001f1fa\U0001f1f8 English", callback_data="lang_en")],
        [InlineKeyboardButton("\U0001f1eb\U0001f1f7 Fran\u00e7ais", callback_data="lang_fr")]
    ]
    await update.message.reply_text(
        T["en"]["choose_lang"],
        reply_markup=InlineKeyboardMarkup(keyboard),
        parse_mode="Markdown"
    )


async def show_main_menu(update_or_query, context, user_id):
    """Show the main menu in user's language."""
    lang = get_lang(user_id)
    tx = T[lang]

    keyboard = [
        [InlineKeyboardButton(tx["products"], callback_data="show_categories"),
         InlineKeyboardButton(tx["balance"], callback_data="check_balance")],
        [InlineKeyboardButton(tx["my_orders"], callback_data="my_orders"),
         InlineKeyboardButton(tx["topup"], callback_data="topup_info")],
        [InlineKeyboardButton(tx["help"], callback_data="help_info")]
    ]
    text = tx["welcome_menu"].format(BOT_NAME)

    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif hasattr(update_or_query, "edit_message_text"):
        await update_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


@require_auth
async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    tx = T[lang]
    text = tx["help_title"].format(BOT_NAME, BINANCE_EMAIL)
    await update.message.reply_text(text, parse_mode="Markdown")


@require_auth
async def categories(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    allowed, msg = SecurityManager.check_rate_limit(user_id, "categories")
    if not allowed:
        await update.message.reply_text(_s("\u23f3 ", msg))
        return
    await update.message.reply_text(T[get_lang(user_id)]["loading"])
    result = await api_client.get_categories()
    if not result["success"]:
        await update.message.reply_text(_s(T[get_lang(user_id)]["error"], ": ", result.get("detail", "Failed")))
        return
    keyboard = []
    for cat in result["data"]["results"]:
        keyboard.append([InlineKeyboardButton(
            _s("\U0001f4c1 ", cat["name"], " (", cat["product_count"], ")"),
            callback_data=_s("cat_", cat["id"]))])
    await update.message.reply_text(
        T[get_lang(user_id)]["categories_title"],
        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


@require_auth
async def products(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    tx = T[lang]
    allowed, msg = SecurityManager.check_rate_limit(user_id, "products")
    if not allowed:
        await update.message.reply_text(_s("\u23f3 ", msg))
        return
    await update.message.reply_text(tx["loading"])
    result = await api_client.get_products(in_stock=True)
    if not result["success"]:
        await update.message.reply_text(_s(tx["error"], ": ", result.get("detail", "Failed")))
        return
    products_data = result["data"]["results"]
    total = result["data"]["count"]
    text = _s("\U0001f4e6 *Products* (", len(products_data), "/", total, ")\n\n")
    keyboard = []
    for prod in products_data[:10]:
        stock = "\u2705" if prod["in_stock"] else "\u274c"
        usd = ngn_to_usd(prod["price"])
        text += _s(stock, " *", prod["name"], "*\n   \U0001f4b0 ", fmt_usd(usd),
                   " | \U0001f4e6 ", prod["stock"], " ", tx["in_stock"], "\n\n")
        if prod["in_stock"]:
            keyboard.append([InlineKeyboardButton(
                _s("\U0001f6d2 ", prod["name"], " - ", fmt_usd(usd)),
                callback_data=_s("buy_", prod["id"]))])
    if not keyboard:
        keyboard.append([InlineKeyboardButton(tx["no_products"], callback_data="noop")])
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


@require_auth
async def balance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    allowed, msg = SecurityManager.check_rate_limit(user_id, "balance_check")
    if not allowed:
        await update.message.reply_text(_s("\u23f3 ", msg))
        return
    bal = db.get_balance(user_id)
    text = T[get_lang(user_id)]["balance_title"].format(fmt_usd(bal))
    await update.message.reply_text(text, parse_mode="Markdown")


@require_auth
async def topup(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    tx = T[lang]
    keyboard = [
        [InlineKeyboardButton(tx["topup_start"], callback_data="start_topup")],
        [InlineKeyboardButton(tx["back"], callback_data="main_menu")]
    ]
    text = tx["topup_title"].format(BINANCE_EMAIL)
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


@require_auth
async def orders(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    tx = T[lang]
    user_orders = db.get_user_orders(user_id)
    if not user_orders:
        await update.message.reply_text(tx["orders_empty"], parse_mode="Markdown")
        return
    text = tx["orders_title"]
    for o in user_orders[:10]:
        cost_usd = float(o["total_cost"])
        text += _s("\U0001f4e6 *", o["product_name"], "*\n   Qty: ", o["quantity"],
                   " | ", fmt_usd(cost_usd), "\n")
        if o.get("keys"):
            key_count = len(o["keys"].split("\n"))
            text += _s("   \U0001f511 ", tx["keys_purchased"].format(key_count), "\n")
        text += "\n"
    await update.message.reply_text(text, parse_mode="Markdown")


# ==================== Callback Handlers ====================

@require_auth
async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data
    user_id = update.effective_user.id

    # Language selection
    if data.startswith("lang_"):
        lang = data.split("_")[1]
        db.set_language(user_id, lang)
        await show_main_menu(query, context, user_id)
        return

    if data == "show_categories":
        await show_categories_callback(query, user_id)
    elif data.startswith("cat_"):
        await show_products_callback(query, int(data.split("_")[1]), user_id)
    elif data == "check_balance":
        await check_balance_callback(query, user_id)
    elif data == "my_orders":
        await show_orders_callback(query, user_id)
    elif data == "topup_info":
        await topup_info_callback(query, user_id)
    elif data == "help_info":
        await help_callback(query, user_id)
    elif data == "main_menu":
        await main_menu_callback(query, user_id)
    elif data.startswith("buy_"):
        await confirm_buy_callback(query, int(data.split("_")[1]), user_id)
    elif data.startswith("confirm_buy_"):
        pid = int(data.split("_")[2])
        qty = int(context.user_data.get("buy_quantity", 1))
        await process_buy_callback(query, pid, qty, user_id, context)
    elif data.startswith("qty_"):
        parts = data.split("_")
        pid, qty = int(parts[1]), int(parts[2])
        context.user_data["buy_quantity"] = qty
        await quantity_callback(query, pid, qty, user_id)
    elif data == "start_topup":
        await start_topup_callback(query, context, user_id)
    elif data == "admin_panel" and user_id == ADMIN_ID:
        await show_admin_panel_callback(query, user_id)
    elif data.startswith("view_order_"):
        order_id = int(data.split("_")[2])
        await view_order_keys_callback(query, order_id, user_id)
    elif data.startswith("admin_"):
        from admin import admin_callback_handler
        await admin_callback_handler(update, context)


async def show_categories_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    result = await api_client.get_categories()
    if not result["success"]:
        await query.edit_message_text(tx["error"])
        return
    keyboard = []
    for cat in result["data"]["results"]:
        keyboard.append([InlineKeyboardButton(
            _s("\U0001f4c1 ", cat["name"], " (", cat["product_count"], ")"),
            callback_data=_s("cat_", cat["id"]))])
    keyboard.append([InlineKeyboardButton(tx["back"], callback_data="main_menu")])
    await query.edit_message_text(tx["categories_title"],
                                   reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_products_callback(query, category_id, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    result = await api_client.get_products(category_id=category_id, in_stock=True)
    if not result["success"]:
        await query.edit_message_text(tx["error"])
        return
    text = "\U0001f4e6 *Products*\n\n"
    keyboard = []
    for prod in result["data"]["results"][:10]:
        usd = ngn_to_usd(prod["price"])
        text += _s("- *", prod["name"], "*\n  \U0001f4b0 ", fmt_usd(usd),
                   " | \U0001f4e6 ", prod["stock"], "\n\n")
        if prod["in_stock"]:
            keyboard.append([InlineKeyboardButton(
                _s("\U0001f6d2 ", prod["name"], " - ", fmt_usd(usd)),
                callback_data=_s("buy_", prod["id"]))])
    keyboard.append([InlineKeyboardButton(tx["back"], callback_data="show_categories")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def check_balance_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    bal = db.get_balance(user_id)
    keyboard = [
        [InlineKeyboardButton(tx["topup"], callback_data="topup_info")],
        [InlineKeyboardButton(tx["back"], callback_data="main_menu")]
    ]
    text = tx["balance_title"].format(fmt_usd(bal))
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_orders_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    user_orders = db.get_user_orders(user_id)
    if not user_orders:
        keyboard = [[InlineKeyboardButton(tx["back"], callback_data="main_menu")]]
        await query.edit_message_text(tx["orders_empty"],
                                      reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
    text = tx["orders_title"]
    keyboard = []
    for o in user_orders[:10]:
        cost_usd = float(o["total_cost"])
        text += _s("\U0001f4e6 *", o["product_name"], "*\n   Qty: ", o["quantity"],
                   " | ", fmt_usd(cost_usd), "\n")
        if o.get("keys"):
            key_count = len(o["keys"].split("\n"))
            text += _s("   \U0001f511 ", tx["keys_purchased"].format(key_count), "\n")
        text += "\n"
        keyboard.append([InlineKeyboardButton(
            _s(tx["view_keys"], o["product_name"]),
            callback_data=_s("view_order_", o["id"]))])
    keyboard.append([InlineKeyboardButton(tx["back"], callback_data="main_menu")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def view_order_keys_callback(query, order_id, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    order = db.get_order_by_id(order_id)
    if not order or order["user_id"] != user_id:
        await query.answer("Order not found.", show_alert=True)
        return
    keys_raw = order.get("keys", "")
    if not keys_raw:
        await query.answer("No keys for this order.", show_alert=True)
        return
    keys = keys_raw.split("\n")
    cost_usd = float(order["total_cost"])
    text = tx["view_keys_title"].format(order["product_name"], order["quantity"], fmt_usd(cost_usd))
    for i, key in enumerate(keys, 1):
        text += tx["key_label"].format(i, key)
    keyboard = [[InlineKeyboardButton(tx["back"], callback_data="my_orders")]]
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def topup_info_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    keyboard = [
        [InlineKeyboardButton(tx["topup_start"], callback_data="start_topup")],
        [InlineKeyboardButton(tx["back"], callback_data="main_menu")]
    ]
    text = tx["topup_info_title"].format(BINANCE_EMAIL)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def help_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    keyboard = [[InlineKeyboardButton(tx["back"], callback_data="main_menu")]]
    text = tx["help_title"].format(BOT_NAME, BINANCE_EMAIL)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def main_menu_callback(query, user_id):
    await show_main_menu(query, None, user_id)


async def confirm_buy_callback(query, product_id, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    keyboard = [
        [InlineKeyboardButton("1\ufe0f\u20e3", callback_data=_s("qty_", product_id, "_1")),
         InlineKeyboardButton("2\ufe0f\u20e3", callback_data=_s("qty_", product_id, "_2")),
         InlineKeyboardButton("3\ufe0f\u20e3", callback_data=_s("qty_", product_id, "_3"))],
        [InlineKeyboardButton("5\ufe0f\u20e3", callback_data=_s("qty_", product_id, "_5")),
         InlineKeyboardButton("10\ufe0f\u20e3", callback_data=_s("qty_", product_id, "_10"))],
        [InlineKeyboardButton(tx["back"], callback_data="show_categories")]
    ]
    await query.edit_message_text(tx["confirm_buy"],
                                   reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def quantity_callback(query, product_id, quantity, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    # Fetch product to show price
    products_result = await api_client.get_products()
    price_text = ""
    if products_result["success"]:
        for p in products_result["data"]["results"]:
            if p["id"] == product_id:
                usd = ngn_to_usd(p["price"]) * quantity
                price_text = fmt_usd(usd)
                break
    keyboard = [
        [InlineKeyboardButton(tx["confirm_btn"], callback_data=_s("confirm_buy_", product_id)),
         InlineKeyboardButton(tx["cancel_btn"], callback_data="show_categories")]
    ]
    text = tx["confirm_title"].format(product_id, quantity, price_text)
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def process_buy_callback(query, product_id, quantity, user_id, context):
    lang = get_lang(user_id)
    tx = T[lang]
    allowed, msg = SecurityManager.check_rate_limit(user_id, "buy")
    if not allowed:
        await query.edit_message_text(_s("\u23f3 ", msg))
        return
    await query.edit_message_text(tx["processing"])
    user_balance = db.get_balance(user_id)

    # Find product using cache (no more multi-page search)
    product = await api_client.find_product(product_id)

    if not product:
        logger.error("Product %d not found in any page", product_id)
        await query.edit_message_text(_s(tx["error"], ": Product not found"))
        return

    total_cost_usd = ngn_to_usd(product["price"]) * quantity
    if user_balance < total_cost_usd:
        text = tx["insufficient"].format(fmt_usd(total_cost_usd), fmt_usd(user_balance))
        await query.edit_message_text(text, parse_mode="Markdown")
        return

    result = await api_client.buy_product(product_id, quantity)
    if not result["success"]:
        logger.error("API buy failed: %s", result.get("detail"))
        await query.edit_message_text(_s(tx["error"], ": ", result.get("detail", "Failed")))
        return

    order_data = result["data"]

    # Save order to database FIRST (before deducting balance)
    order_keys = order_data.get("keys", [])
    order_api_id = order_data.get("order_id")
    logger.info("Saving order: user=%d product=%d name=%s qty=%d cost=%.2f keys=%s api_id=%s",
                user_id, product_id, product["name"], quantity, total_cost_usd,
                str(order_keys)[:100], order_api_id)

    order_saved = False
    try:
        keys_str = "\n".join(order_keys) if order_keys else ""
        conn = db.get_db()
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO bot_orders (user_id, product_id, product_name, quantity, total_cost, `keys`, order_id_api) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (user_id, product_id, product["name"], quantity, total_cost_usd, keys_str, order_api_id)
            )
        conn.commit()
        db.return_db(conn)
        order_saved = True
        logger.info("Order saved OK for user %d (id=%s)", user_id, order_api_id)
    except Exception as e:
        logger.error("ORDER SAVE FAILED: %s", e)

    if not order_saved:
        await query.edit_message_text(_s(tx["error"], ": Order could not be saved. Contact support."))
        return

    # Only deduct balance AFTER order is saved
    db.update_balance(user_id, -total_cost_usd)

    keys_text = ""
    for k in order_data.get("keys", []):
        keys_text += _s("\U0001f511 `", k, "`\n")
    keyboard = [
        [InlineKeyboardButton(tx["my_orders"], callback_data="my_orders")],
        [InlineKeyboardButton(tx["back"], callback_data="main_menu")]
    ]
    # charge from API is total in NGN, convert to USD
    charge_ngn = float(order_data.get("charge", 0)) or float(product["price"]) * quantity
    charge = ngn_to_usd(charge_ngn)
    text = tx["purchase_ok"].format(
        order_data.get("product", product["name"]),
        order_data.get("quantity", quantity),
        fmt_usd(charge),
        keys_text
    )
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def start_topup_callback(query, context, user_id):
    context.user_data["awaiting_topup_amount"] = True
    context.user_data.pop("awaiting_topup_txid", None)
    context.user_data.pop("awaiting_topup_binance_id", None)
    context.user_data.pop("topup_amount", None)
    lang = get_lang(user_id)
    tx = T[lang]
    await query.edit_message_text(tx["topup_title"].format(BINANCE_EMAIL), parse_mode="Markdown")


async def show_admin_panel_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    keyboard = [[InlineKeyboardButton("\U0001f310 Open Web Admin", url="http://localhost:5000")]]
    await query.edit_message_text(tx["admin_panel"],
                                   reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def handle_text_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    tx = T[lang]

    if context.user_data.get("awaiting_topup_amount"):
        context.user_data["awaiting_topup_amount"] = False
        try:
            amount = float(update.message.text.replace(",", "").replace("$", ""))
            is_valid, msg = SecurityManager.validate_amount(amount)
            if not is_valid:
                await update.message.reply_text(_s("\u274c ", msg))
                return
            allowed, msg = SecurityManager.check_rate_limit(user_id, "topup")
            if not allowed:
                await update.message.reply_text(_s("\u23f3 ", msg))
                return
            context.user_data["topup_amount"] = amount
            context.user_data["awaiting_topup_txid"] = True
            await update.message.reply_text(tx["topup_step2"], parse_mode="Markdown")
        except ValueError:
            await update.message.reply_text("\u274c Please enter a valid number.")

    elif context.user_data.get("awaiting_topup_txid"):
        txid = update.message.text.strip()
        if len(txid) < 5:
            await update.message.reply_text("\u274c Invalid TXID.")
            return
        context.user_data["topup_txid"] = txid
        context.user_data["awaiting_topup_txid"] = False
        context.user_data["awaiting_topup_binance_id"] = True
        await update.message.reply_text(tx["topup_step3"], parse_mode="Markdown")

    elif context.user_data.get("awaiting_topup_binance_id"):
        binance_id = update.message.text.strip()
        if len(binance_id) < 3:
            await update.message.reply_text("\u274c Invalid Binance ID.")
            return
        context.user_data["awaiting_topup_binance_id"] = False
        amount = context.user_data.pop("topup_amount", 0)
        txid = context.user_data.pop("topup_txid", "")

        if db.create_topup_request(user_id, amount, txid, binance_id):
            try:
                admin_id = int(os.getenv("ADMIN_ID", 0))
                username = update.effective_user.username or update.effective_user.first_name
                admin_msg = _s(
                    "\U0001f4b0 *New Top Up Request*\n\n",
                    "User: @", str(username), " (`", str(user_id), "`)\n",
                    "Amount: $", "{:,.2f}".format(amount), "\n",
                    "TXID: `", txid, "`\n",
                    "Binance ID: `", binance_id, "`"
                )
                await context.bot.send_message(chat_id=admin_id, text=admin_msg, parse_mode="Markdown")
            except Exception:
                pass
            text = tx["topup_submitted"].format(fmt_usd(amount), txid, binance_id)
            await update.message.reply_text(text, parse_mode="Markdown")
        else:
            await update.message.reply_text("\u274c Failed to submit topup request.")


@require_auth
async def admin_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    admin_id = int(os.getenv("ADMIN_ID", 0))
    if user_id != admin_id:
        await update.message.reply_text(T[get_lang(user_id)]["access_denied"])
        return
    keyboard = [[InlineKeyboardButton("\U0001f310 Open Web Admin", url="http://localhost:5000")]]
    text = T[get_lang(user_id)]["admin_panel"]
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


def send_telegram_msg(chat_id, text):
    """Send a message via Telegram Bot API."""
    if not BOT_TOKEN or not chat_id:
        return
    url = "https://api.telegram.org/bot" + BOT_TOKEN + "/sendMessage"
    data = json.dumps({"chat_id": chat_id, "text": text}).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
    try:
        urllib.request.urlopen(req, timeout=10)
    except Exception:
        pass


def stock_checker_loop():
    """Background task: check stock every 5 minutes and broadcast restocks."""
    import asyncio
    first_run = True

    async def check():
        nonlocal first_run
        try:
            result = await api_client.get_products()
            if not result["success"]:
                return

            products = result["data"]["results"]
            cats_result = await api_client.get_categories()
            cat_map = {}
            if cats_result["success"]:
                for c in cats_result["data"]["results"]:
                    cat_map[c["id"]] = c["name"]

            for p in products:
                cat_name = cat_map.get(p["category_id"], "")
                restocked = db.upsert_stock(
                    p["id"], p["name"], cat_name,
                    p["stock"], p["in_stock"],
                    skip_alert=first_run
                )
            if first_run:
                first_run = False
                logger.info("Stock tracker seeded, alerts enabled for next checks")
                if restocked:
                    # Broadcast restock to all users
                    users = db.get_all_users()
                    msg = (
                        "\U0001f525 *Restock Alert!*\n\n"
                        + "*" + p["name"] + "* is back in stock!\n"
                        + "\U0001f4b0 Price: " + "${:,.2f}".format(ngn_to_usd(p["price"])) + "\n"
                        + "\U0001f4e6 Stock: " + str(p["stock"]) + " available\n\n"
                        + "Use /products to buy now!"
                    )
                    sent = 0
                    for u in users:
                        try:
                            send_telegram_msg(u["telegram_id"], msg)
                            sent += 1
                        except Exception:
                            pass
                    logger.info("Restock broadcast for %s sent to %d users", p["name"], sent)
        except Exception as e:
            logger.error("Stock checker error: %s", e)

    loop = asyncio.new_event_loop()
    while True:
        time.sleep(300)  # Check every 5 minutes
        try:
            loop.run_until_complete(check())
        except Exception as e:
            logger.error("Stock checker loop error: %s", e)


def start_web_admin():
    from admin_web import run_web_admin
    run_web_admin(port=5000)

def main():
    db.init_db()
    web_thread = threading.Thread(target=start_web_admin, daemon=True)
    web_thread.start()
    stock_thread = threading.Thread(target=stock_checker_loop, daemon=True)
    stock_thread.start()
    application = Application.builder().token(BOT_TOKEN).build()
    application.bot_data["admin_id"] = ADMIN_ID
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("categories", categories))
    application.add_handler(CommandHandler("products", products))
    application.add_handler(CommandHandler("balance", balance))
    application.add_handler(CommandHandler("topup", topup))
    application.add_handler(CommandHandler("orders", orders))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    print("Bot " + BOT_NAME + " is starting...")
    print("Web admin panel: http://localhost:5000")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
