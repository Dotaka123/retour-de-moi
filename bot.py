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
from proxy_api import proxy_api, BOT_PACKAGE_IDS

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


async def safe_edit(query, text, reply_markup=None, parse_mode=None):
    """Try to edit message; if it fails (too old, deleted, too long), send new one."""
    try:
        await query.edit_message_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
    except Exception:
        try:
            await query.message.reply_text(text, reply_markup=reply_markup, parse_mode=parse_mode)
        except Exception:
            pass


def ngn_to_usd(ngn_price):
    """Convert NGN price from API to USD (bot price = API price / 2)."""
    return float(ngn_price) / NGN_TO_USD / 2


def get_product_price_usd(product):
    """Get the USD price for a product, checking for admin override first."""
    pid = product["id"]
    override = db.get_product_override(pid)
    if override and override["custom_price"]:
        return float(override["price_usd"])
    return ngn_to_usd(product["price"])


def get_product_stock(product):
    """Get stock for a product, checking for admin override first."""
    pid = product["id"]
    override = db.get_product_override(pid)
    if override and override["stock"] >= 0:
        return override["stock"]
    return product["stock"]


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
        "day_label": "day(s)",
        "hour_label": "hour(s)",
        "proxy_btn": "\U0001f5a7\ufe0f Proxy",
        "proxy_packages_title": "\U0001f4e6 *Choose a Proxy Package*\n\nSelect a package:",
        "proxy_countries_title": "\U0001f30d *Choose a Country*\n\nPackage: *{}*\n\nSelect a country:",
        "proxy_durations_title": "\u23f1 *Choose Duration*\n\nPackage: *{}*\nCountry: *{}*\n\nSelect a duration:",
        "proxy_protocol_title": "\U0001f500 *Choose Protocol*\n\nPackage: *{}*\nCountry: *{}*\nDuration: *{}*\nPrice: *{}*\n\nSelect the connection protocol:",
        "proxy_confirm_title": "\U0001f6d2 *Confirm Purchase*\n\nPackage: *{}*\nCountry: *{}*\nDuration: *{}*\nProtocol: *{}*\nPrice: *{}*\n\nTap Confirm to create your proxy. The amount is deducted from your balance.",
        "proxy_no_parent": "\u274c No parent proxy is available in this country for this package right now. Please choose another country.",
        "proxy_processing": "\u23f3 Creating your proxy...",
        "proxy_insufficient": "\u274c *Insufficient Balance*\n\nRequired: {}\nYour balance: {}\n\nUse /topup to add funds.",
        "proxy_ok": "\u2705 *Proxy Created!*\n\nPackage: *{}*\nCountry: *{}*\nDuration: *{}*\nProtocol: *{}*\nCost: *{}*\n\n*Your Proxy:*\n`{}`\n\n\u26a0\ufe0f Save these credentials and respect the allowed usage.",
        "proxy_failed": "\u274c Failed to create the proxy. Please contact support.",
        "proxy_my_orders": "\U0001f5a7\ufe0f My Proxies",
        "proxy_orders_title": "\U0001f5a7\ufe0f *Your Proxy Orders*\n\n",
        "proxy_orders_empty": "\U0001f5a7\ufe0f *Your Proxy Orders*\n\nNo proxies yet!",
        "proxy_view": "View",
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
        "day_label": "jour(s)",
        "hour_label": "heure(s)",
        "proxy_btn": "\U0001f5a7\ufe0f Proxy",
        "proxy_packages_title": "\U0001f4e6 *Choisissez un Package Proxy*\n\nS\u00e9lectionnez un package :",
        "proxy_countries_title": "\U0001f30d *Choisissez un Pays*\n\nPackage : *{}*\n\nS\u00e9lectionnez un pays :",
        "proxy_durations_title": "\u23f1 *Choisissez la Dur\u00e9e*\n\nPackage : *{}*\nPays : *{}*\n\nS\u00e9lectionnez une dur\u00e9e :",
        "proxy_protocol_title": "\U0001f500 *Choisissez le Protocole*\n\nPackage : *{}*\nPays : *{}*\nDur\u00e9e : *{}*\nPrix : *{}*\n\nS\u00e9lectionnez le protocole de connexion :",
        "proxy_confirm_title": "\U0001f6d2 *Confirmer l'Achat*\n\nPackage : *{}*\nPays : *{}*\nDur\u00e9e : *{}*\nProtocole : *{}*\nPrix : *{}*\n\nAppuyez sur Confirmer pour cr\u00e9er votre proxy. Le montant sera d\u00e9duit de votre solde.",
        "proxy_no_parent": "\u274c Aucun proxy parent n'est disponible dans ce pays pour ce package pour le moment. Choisissez un autre pays.",
        "proxy_processing": "\u23f3 Cr\u00e9ation de votre proxy...",
        "proxy_insufficient": "\u274c *Solde Insuffisant*\n\nRequis : {}\nVotre solde : {}\n\nUtilisez /topup pour ajouter des fonds.",
        "proxy_ok": "\u2705 *Proxy Cr\u00e9\u00e9 !*\n\nPackage : *{}*\nPays : *{}*\nDur\u00e9e : *{}*\nProtocole : *{}*\nCo\u00fbt : *{}*\n\n*Votre Proxy :*\n`{}`\n\n\u26a0\ufe0f Sauvegardez ces informations et respectez l'utilisation autoris\u00e9e.",
        "proxy_failed": "\u274c \u00c9chec de la cr\u00e9ation du proxy. Contactez le support.",
        "proxy_my_orders": "\U0001f5a7\ufe0f Mes Proxies",
        "proxy_orders_title": "\U0001f5a7\ufe0f *Vos Commandes Proxy*\n\n",
        "proxy_orders_empty": "\U0001f5a7\ufe0f *Vos Commandes Proxy*\n\nAucun proxy pour le moment !",
        "proxy_view": "Voir",
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
        [InlineKeyboardButton(tx["proxy_btn"], callback_data="px_menu"),
         InlineKeyboardButton(tx["help"], callback_data="help_info")]
    ]
    text = tx["welcome_menu"].format(BOT_NAME)

    if hasattr(update_or_query, "message") and update_or_query.message:
        await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
    elif hasattr(update_or_query, "edit_message_text"):
        try:
            await update_or_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        except Exception:
            try:
                await update_or_query.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
            except Exception:
                pass


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
        usd = get_product_price_usd(prod)
        display_stock = get_product_stock(prod)
        text += _s(stock, " *", prod["name"], "*\n   \U0001f4b0 ", fmt_usd(usd),
                   " | \U0001f4e6 ", display_stock, " ", tx["in_stock"], "\n\n")
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

async def callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("\u23f3")
    data = query.data
    user_id = update.effective_user.id

    # Quick auth check (no heavy DB calls)
    user = db.get_user(user_id)
    if not user:
        db.create_user(user_id, update.effective_user.username, update.effective_user.first_name)
    elif user.get("is_banned"):
        await safe_edit(query, "\u274c Your account has been suspended.")
        return

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
    elif data == "px_menu":
        await px_packages_callback(query, user_id)
    elif data.startswith("px_pkg_"):
        parts = data.split("_")
        pkg_id = int(parts[2])
        await px_countries_callback(query, pkg_id, user_id)
    elif data.startswith("px_country_"):
        parts = data.split("_")
        pkg_id, country_id = int(parts[2]), int(parts[3])
        await px_durations_callback(query, pkg_id, country_id, user_id)
    elif data.startswith("px_dur_"):
        parts = data.split("_")
        pkg_id, country_id, days, hours = int(parts[2]), int(parts[3]), int(parts[4]), int(parts[5])
        await px_protocol_callback(query, pkg_id, country_id, days, hours, user_id)
    elif data.startswith("px_proto_"):
        parts = data.split("_")
        pkg_id, country_id = int(parts[2]), int(parts[3])
        days, hours = int(parts[4]), int(parts[5])
        protocol = parts[6]
        await px_confirm_callback(query, pkg_id, country_id, days, hours, protocol, user_id)
    elif data.startswith("px_buy_"):
        parts = data.split("_")
        pkg_id, country_id = int(parts[2]), int(parts[3])
        days, hours = int(parts[4]), int(parts[5])
        protocol = parts[6]
        await px_buy_callback(query, context, pkg_id, country_id, days, hours, protocol, user_id)
    elif data == "px_my_orders":
        await px_orders_callback(query, user_id)
    elif data.startswith("admin_"):
        from admin import admin_callback_handler
        await admin_callback_handler(update, context)


async def show_categories_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    result = await api_client.get_categories()
    if not result["success"]:
        await safe_edit(query, tx["error"])
        return
    keyboard = []
    for cat in result["data"]["results"]:
        keyboard.append([InlineKeyboardButton(
            _s("\U0001f4c1 ", cat["name"], " (", cat["product_count"], ")"),
            callback_data=_s("cat_", cat["id"]))])
    keyboard.append([InlineKeyboardButton(tx["back"], callback_data="main_menu")])
    await safe_edit(query, tx["categories_title"],
                                   reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_products_callback(query, category_id, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    result = await api_client.get_products(category_id=category_id, in_stock=True)
    if not result["success"]:
        await safe_edit(query, tx["error"])
        return
    text = "\U0001f4e6 *Products*\n\n"
    keyboard = []
    for prod in result["data"]["results"][:10]:
        usd = get_product_price_usd(prod)
        display_stock = get_product_stock(prod)
        text += _s("- *", prod["name"], "*\n  \U0001f4b0 ", fmt_usd(usd),
                   " | \U0001f4e6 ", display_stock, "\n\n")
        if prod["in_stock"]:
            keyboard.append([InlineKeyboardButton(
                _s("\U0001f6d2 ", prod["name"], " - ", fmt_usd(usd)),
                callback_data=_s("buy_", prod["id"]))])
    keyboard.append([InlineKeyboardButton(tx["back"], callback_data="show_categories")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def check_balance_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    bal = db.get_balance(user_id)
    keyboard = [
        [InlineKeyboardButton(tx["topup"], callback_data="topup_info")],
        [InlineKeyboardButton(tx["back"], callback_data="main_menu")]
    ]
    text = tx["balance_title"].format(fmt_usd(bal))
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def show_orders_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    user_orders = db.get_user_orders(user_id)
    if not user_orders:
        keyboard = [[InlineKeyboardButton(tx["back"], callback_data="main_menu")]]
        await safe_edit(query, tx["orders_empty"],
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
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


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
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


def format_duration(days, hours, lang):
    """Format a plan duration in the user's language."""
    tx = T[lang]
    if days > 0:
        return _s(days, " ", tx["day_label"])
    return _s(hours, " ", tx["hour_label"])


async def _px_enabled_plans():
    """Return enabled proxy plans (Golden=1, Silver=2), merging DB overrides with API base prices."""
    saved = {f"{r['pkg_id']}_{r['days']}_{r['hours']}": r for r in db.get_all_proxy_prices()}
    plans = {}
    for pid in BOT_PACKAGE_IDS:
        prices_result = await proxy_api.get_prices(pid)
        if not prices_result["success"]:
            continue
        for p in prices_result.get("data", []) or []:
            days = int(float(p.get("days", 0) or 0))
            hours = int(p.get("hours", 0) or 0)
            base = float(p.get("price", 0))
            key = f"{pid}_{days}_{hours}"
            saved_row = saved.get(key)
            sell = float(saved_row["sell_price"]) if saved_row and saved_row["sell_price"] is not None else base
            enabled = bool(saved_row["enabled"]) if saved_row else True
            plans[key] = {
                "pkg_id": pid,
                "days": days,
                "hours": hours,
                "base_price": base,
                "sell_price": sell,
                "enabled": enabled,
            }
    result = [v for v in plans.values() if v["enabled"]]
    for p in result:
        p["package_name"] = "Golden Package" if p["pkg_id"] == 1 else (
            "Silver Package" if p["pkg_id"] == 2 else "Package " + str(p["pkg_id"]))
    result.sort(key=lambda x: (x["pkg_id"], x["days"], x["hours"]))
    return result


async def _px_plan(pkg_id, days, hours):
    """Return a single plan dict (with sell_price/enabled/names) using DB override or API base."""
    plans = await _px_enabled_plans()
    for p in plans:
        if p["pkg_id"] == pkg_id and p["days"] == days and p["hours"] == hours:
            return p
    return None


async def px_packages_callback(query, user_id):
    """Step 1: choose a proxy package (Golden / Silver)."""
    lang = get_lang(user_id)
    tx = T[lang]
    text, keyboard = await _px_packages_view(lang)
    if not keyboard:
        await safe_edit(query, _s(tx["proxy_err"], ": No plans configured."), parse_mode="Markdown")
        return
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def _px_packages_view(lang):
    """Build the package-selection view. Returns (text, keyboard)."""
    tx = T[lang]
    plans = await _px_enabled_plans()
    pkg_ids = sorted(set(p["pkg_id"] for p in plans))
    if not pkg_ids:
        return tx["proxy_packages_title"], []
    # Fetch package names from proxy API
    pkg_result = await proxy_api.get_packages()
    pkg_names = {}
    if pkg_result["success"]:
        for p in pkg_result["data"]:
            pkg_names[p["id"]] = p["package_name"]

    keyboard = []
    for pid in BOT_PACKAGE_IDS:
        if pid in pkg_ids:
            keyboard.append([InlineKeyboardButton(
                "\U0001f4e6 " + pkg_names.get(pid, "Package " + str(pid)),
                callback_data=_s("px_pkg_", pid))])
    keyboard.append([InlineKeyboardButton(tx["proxy_my_orders"], callback_data="px_my_orders")])
    keyboard.append([InlineKeyboardButton(tx["back"], callback_data="main_menu")])
    return tx["proxy_packages_title"], keyboard


async def px_countries_callback(query, pkg_id, user_id):
    """Step 2: choose a country for the selected package."""
    lang = get_lang(user_id)
    tx = T[lang]
    result = await proxy_api.get_countries(pkg_id)
    if not result["success"]:
        await safe_edit(query, tx["proxy_err"], parse_mode="Markdown")
        return
    countries = result["data"]
    pkg_result = await proxy_api.get_packages()
    pkg_names = {}
    if pkg_result["success"]:
        for p in pkg_result["data"]:
            pkg_names[p["id"]] = p["package_name"]
    pkg_name = pkg_names.get(pkg_id, "Package " + str(pkg_id))

    keyboard = [
        [InlineKeyboardButton(_s("\U0001f30d ", c["country_name"]),
                              callback_data=_s("px_country_", pkg_id, "_", c["id"]))]
        for c in countries
    ]
    keyboard.append([InlineKeyboardButton(tx["back"], callback_data="px_menu")])
    text = tx["proxy_countries_title"].format(pkg_name)
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def px_durations_callback(query, pkg_id, country_id, user_id):
    """Step 3: choose a duration (from enabled plans) for the package."""
    lang = get_lang(user_id)
    tx = T[lang]
    plans = await _px_enabled_plans()
    plans = [p for p in plans if p["pkg_id"] == pkg_id and p["enabled"]]

    # Get country & package names
    pkg_result = await proxy_api.get_packages()
    pkg_names = {}
    if pkg_result["success"]:
        for p in pkg_result["data"]:
            pkg_names[p["id"]] = p["package_name"]
    pkg_name = pkg_names.get(pkg_id, "Package " + str(pkg_id))
    country_name = "?"
    country_result = await proxy_api.get_countries(pkg_id)
    if country_result["success"]:
        for c in country_result["data"]:
            if c["id"] == country_id:
                country_name = c["country_name"]
                break

    if not plans:
        await safe_edit(query, _s(tx["proxy_err"], ": No plans configured."), parse_mode="Markdown")
        return

    keyboard = []
    for p in plans:
        days, hours = int(p["days"]), int(p["hours"])
        price = float(p["sell_price"])
        label = _s("\u23f1 ", format_duration(days, hours, lang), " - ", fmt_usd(price))
        keyboard.append([InlineKeyboardButton(
            label,
            callback_data=_s("px_dur_", pkg_id, "_", country_id, "_", days, "_", hours))])
    keyboard.append([InlineKeyboardButton(tx["back"], callback_data=_s("px_pkg_", pkg_id))])
    text = tx["proxy_durations_title"].format(pkg_name, country_name)
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def px_protocol_callback(query, pkg_id, country_id, days, hours, user_id):
    """Step 4: choose protocol (HTTP / SOCKS)."""
    lang = get_lang(user_id)
    tx = T[lang]
    plan = await _px_plan(pkg_id, days, hours)
    if not plan:
        await safe_edit(query, _s(tx["proxy_err"], ": Plan not found."), parse_mode="Markdown")
        return
    sell_price = float(plan["sell_price"])

    pkg_result = await proxy_api.get_packages()
    pkg_names = {}
    if pkg_result["success"]:
        for p in pkg_result["data"]:
            pkg_names[p["id"]] = p["package_name"]
    pkg_name = pkg_names.get(pkg_id, "Package " + str(pkg_id))
    country_name = "?"
    country_result = await proxy_api.get_countries(pkg_id)
    if country_result["success"]:
        for c in country_result["data"]:
            if c["id"] == country_id:
                country_name = c["country_name"]
                break

    keyboard = [
        [InlineKeyboardButton("HTTP", callback_data=_s("px_proto_", pkg_id, "_", country_id, "_", days, "_", hours, "_http"))],
        [InlineKeyboardButton("SOCKS", callback_data=_s("px_proto_", pkg_id, "_", country_id, "_", days, "_", hours, "_socks"))],
        [InlineKeyboardButton(tx["back"], callback_data=_s("px_dur_", pkg_id, "_", country_id, "_", days, "_", hours))]
    ]
    text = tx["proxy_protocol_title"].format(pkg_name, country_name,
                                             format_duration(days, hours, lang), fmt_usd(sell_price))
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def px_confirm_callback(query, pkg_id, country_id, days, hours, protocol, user_id):
    """Step 5: confirm the proxy purchase."""
    lang = get_lang(user_id)
    tx = T[lang]
    plan = await _px_plan(pkg_id, days, hours)
    if not plan:
        await safe_edit(query, _s(tx["proxy_err"], ": Plan not found."), parse_mode="Markdown")
        return
    sell_price = float(plan["sell_price"])
    if sell_price <= 0:
        await safe_edit(query, _s(tx["proxy_err"], ": Price not configured."), parse_mode="Markdown")
        return

    pkg_result = await proxy_api.get_packages()
    pkg_names = {}
    if pkg_result["success"]:
        for p in pkg_result["data"]:
            pkg_names[p["id"]] = p["package_name"]
    pkg_name = pkg_names.get(pkg_id, "Package " + str(pkg_id))
    country_name = "?"
    country_result = await proxy_api.get_countries(pkg_id)
    if country_result["success"]:
        for c in country_result["data"]:
            if c["id"] == country_id:
                country_name = c["country_name"]
                break

    keyboard = [
        [InlineKeyboardButton(tx["confirm_btn"],
                              callback_data=_s("px_buy_", pkg_id, "_", country_id, "_", days, "_", hours, "_", protocol)),
         InlineKeyboardButton(tx["cancel_btn"], callback_data="px_menu")],
        [InlineKeyboardButton(tx["back"], callback_data=_s("px_proto_", pkg_id, "_", country_id, "_", days, "_", hours, "_", protocol))]
    ]
    text = tx["proxy_confirm_title"].format(
        pkg_name, country_name, format_duration(days, hours, lang), protocol.upper(), fmt_usd(sell_price))
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def px_buy_callback(query, context, pkg_id, country_id, days, hours, protocol, user_id):
    """Execute the proxy purchase: check balance, create proxy via API, deduct wallet, save order."""
    lang = get_lang(user_id)
    tx = T[lang]
    plan = await _px_plan(pkg_id, days, hours)
    if not plan:
        await safe_edit(query, _s(tx["proxy_err"], ": Plan not found."), parse_mode="Markdown")
        return
    sell_price = float(plan["sell_price"])
    base_price = float(plan["base_price"]) if plan["base_price"] is not None else sell_price
    balance = db.get_balance(user_id)

    allowed, msg = SecurityManager.check_rate_limit(user_id, "buy")
    if not allowed:
        await safe_edit(query, _s("\u23f3 ", msg))
        return
    if balance < sell_price:
        text = tx["proxy_insufficient"].format(fmt_usd(sell_price), fmt_usd(balance))
        await safe_edit(query, text, parse_mode="Markdown")
        return

    await safe_edit(query, tx["proxy_processing"], parse_mode="Markdown")

    # Get names
    pkg_result = await proxy_api.get_packages()
    pkg_names = {}
    if pkg_result["success"]:
        for p in pkg_result["data"]:
            pkg_names[p["id"]] = p["package_name"]
    pkg_name = pkg_names.get(pkg_id, "Package " + str(pkg_id))
    country_name = "?"
    country_result = await proxy_api.get_countries(pkg_id)
    if country_result["success"]:
        for c in country_result["data"]:
            if c["id"] == country_id:
                country_name = c["country_name"]
                break

    # Pick an available parent proxy for this country + package
    pp_result = await proxy_api.get_parent_proxies(pkg_id, country_id)
    if not pp_result["success"] or not pp_result["data"].get("list"):
        await safe_edit(query, tx["proxy_no_parent"], parse_mode="Markdown")
        return
    available = [pp for pp in pp_result["data"]["list"] if pp.get("is_available")]
    if not available:
        await safe_edit(query, tx["proxy_no_parent"], parse_mode="Markdown")
        return
    parent = available[0]
    parent_proxy_id = parent["id"]

    # Duration value for the API
    duration = float(days) if days > 0 else float(hours) / 100.0

    result = await proxy_api.create_proxy(parent_proxy_id, pkg_id, protocol, duration)
    if not result["success"]:
        logger.error("Proxy creation failed: %s", result.get("detail"))
        await safe_edit(query, _s(tx["proxy_failed"], "\n", str(result.get("detail", ""))))
        return

    proxy_data = result["data"]
    db.update_balance(user_id, -sell_price)

    proxy_details = _proxy_to_str(proxy_data)
    db.create_proxy_order(
        user_id, country_name, pkg_name, protocol.title(), days, hours,
        base_price, sell_price, parent_proxy_id, proxy_details
    )

    keyboard = [
        [InlineKeyboardButton(tx["proxy_my_orders"], callback_data="px_my_orders")],
        [InlineKeyboardButton(tx["back"], callback_data="main_menu")]
    ]
    text = tx["proxy_ok"].format(
        pkg_name, country_name, format_duration(days, hours, lang),
        protocol.upper(), fmt_usd(sell_price), proxy_details)
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


def _proxy_to_str(data):
    """Build a proxy connection string from the create-proxy API response."""
    if not isinstance(data, dict):
        return str(data)
    parts = []
    username = data.get("username")
    password = data.get("password")
    ip_addr = data.get("ip_addr")
    port = data.get("port") or data.get("http_port") or data.get("socks_port")
    protocol = data.get("type") or ""
    expire = data.get("expire_at")
    if username and password and ip_addr and port:
        proto = (protocol or "http").lower()
        parts.append(f"{proto}://{username}:{password}@{ip_addr}:{port}")
    elif ip_addr and port:
        parts.append(f"{ip_addr}:{port}")
    if username:
        parts.append("Username: " + str(username))
    if password:
        parts.append("Password: " + str(password))
    if ip_addr:
        parts.append("IP: " + str(ip_addr))
    if port:
        parts.append("Port: " + str(port))
    if protocol:
        parts.append("Type: " + str(protocol))
    if expire:
        parts.append("Expires: " + str(expire))
    return "\n".join(parts) if parts else str(data)


async def px_orders_callback(query, user_id):
    """Show the user's proxy orders."""
    lang = get_lang(user_id)
    tx = T[lang]
    orders = db.get_user_proxy_orders(user_id)
    if not orders:
        keyboard = [[InlineKeyboardButton(tx["back"], callback_data="px_menu")]]
        await safe_edit(query, tx["proxy_orders_empty"],
                        reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")
        return
    text = tx["proxy_orders_title"]
    keyboard = []
    for o in orders[:10]:
        cost = float(o["sell_price"])
        text += _s("\U0001f5a7\ufe0f *", o["package_name"], "*\n")
        text += _s("   ", o["country_name"], " | ", format_duration(int(o["plan_days"]), int(o["plan_hours"]), lang),
                   " | ", o["protocol"].upper(), " | ", fmt_usd(cost), "\n")
        if o.get("proxy_details"):
            text += _s("   `", o["proxy_details"], "`\n")
        text += "\n"
    keyboard.append([InlineKeyboardButton(tx["back"], callback_data="px_menu")])
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def topup_info_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    keyboard = [
        [InlineKeyboardButton(tx["topup_start"], callback_data="start_topup")],
        [InlineKeyboardButton(tx["back"], callback_data="main_menu")]
    ]
    text = tx["topup_info_title"].format(BINANCE_EMAIL)
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def help_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    keyboard = [[InlineKeyboardButton(tx["back"], callback_data="main_menu")]]
    text = tx["help_title"].format(BOT_NAME, BINANCE_EMAIL)
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


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
    await safe_edit(query, tx["confirm_buy"],
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
                usd = get_product_price_usd(p) * quantity
                price_text = fmt_usd(usd)
                break
    keyboard = [
        [InlineKeyboardButton(tx["confirm_btn"], callback_data=_s("confirm_buy_", product_id)),
         InlineKeyboardButton(tx["cancel_btn"], callback_data="show_categories")]
    ]
    text = tx["confirm_title"].format(product_id, quantity, price_text)
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def process_buy_callback(query, product_id, quantity, user_id, context):
    lang = get_lang(user_id)
    tx = T[lang]
    allowed, msg = SecurityManager.check_rate_limit(user_id, "buy")
    if not allowed:
        await safe_edit(query, _s("\u23f3 ", msg))
        return
    await safe_edit(query, tx["processing"])
    user_balance = db.get_balance(user_id)

    # Find product using cache (no more multi-page search)
    product = await api_client.find_product(product_id)

    if not product:
        logger.error("Product %d not found in any page", product_id)
        await safe_edit(query, _s(tx["error"], ": Product not found"))
        return

    total_cost_usd = get_product_price_usd(product) * quantity
    if user_balance < total_cost_usd:
        text = tx["insufficient"].format(fmt_usd(total_cost_usd), fmt_usd(user_balance))
        await safe_edit(query, text, parse_mode="Markdown")
        return

    result = await api_client.buy_product(product_id, quantity)
    if not result["success"]:
        logger.error("API buy failed: %s", result.get("detail"))
        await safe_edit(query, _s(tx["error"], ": ", result.get("detail", "Failed")))
        return

    order_data = result["data"]

    # Save order to database FIRST (before deducting balance)
    order_keys = order_data.get("keys", [])
    order_api_id = order_data.get("order_id")
    logger.info("Saving order: user=%d product=%d name=%s qty=%d cost=%.2f keys=%s api_id=%s",
                user_id, product_id, product["name"], quantity, total_cost_usd,
                str(order_keys)[:100], order_api_id)

    # Convert key dicts to displayable strings
    def _key_to_str(k):
        if isinstance(k, dict):
            parts = []
            if k.get("details"):
                parts.append(k["details"].replace("\n", " | "))
            if k.get("link"):
                parts.append("Link: " + k["link"])
            return " | ".join(parts) if parts else str(k)
        return str(k) if k else ""

    clean_keys = [_key_to_str(k) for k in order_keys if k] if order_keys else []

    order_saved = db.create_order(
        user_id, product_id, product["name"],
        quantity, float(total_cost_usd), clean_keys, order_api_id
    )
    if not order_saved:
        logger.error("ORDER SAVE FAILED: user=%d product=%d name=%s qty=%d cost=%.2f keys_count=%s api_id=%s",
                     user_id, product_id, product.get('name'), quantity, total_cost_usd,
                     len(clean_keys), order_api_id)
        await safe_edit(query, _s(tx["error"], ": Order could not be saved. Contact support."))
        return
    logger.info("Order saved OK for user %d (id=%s)", user_id, order_api_id)

    # Only deduct balance AFTER order is saved
    db.update_balance(user_id, -total_cost_usd)

    keys_text = ""
    for k in order_data.get("keys", []):
        key_str = _key_to_str(k)
        keys_text += _s("\U0001f511 `", key_str, "`\n")
    keyboard = [
        [InlineKeyboardButton(tx["my_orders"], callback_data="my_orders")],
        [InlineKeyboardButton(tx["back"], callback_data="main_menu")]
    ]
    # charge from API is total in NGN, convert to USD
    charge_usd = get_product_price_usd(product) * quantity
    charge = charge_usd
    text = tx["purchase_ok"].format(
        order_data.get("product", product["name"]),
        order_data.get("quantity", quantity),
        fmt_usd(charge),
        keys_text
    )
    await safe_edit(query, text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


async def start_topup_callback(query, context, user_id):
    context.user_data["awaiting_topup_amount"] = True
    context.user_data.pop("awaiting_topup_txid", None)
    context.user_data.pop("awaiting_topup_binance_id", None)
    context.user_data.pop("topup_amount", None)
    lang = get_lang(user_id)
    tx = T[lang]
    await safe_edit(query, tx["topup_title"].format(BINANCE_EMAIL), parse_mode="Markdown")


async def show_admin_panel_callback(query, user_id):
    lang = get_lang(user_id)
    tx = T[lang]
    keyboard = [[InlineKeyboardButton("\U0001f310 Open Web Admin", url="http://localhost:5000")]]
    await safe_edit(query, tx["admin_panel"],
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
async def proxies_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Open the proxy sales section."""
    user_id = update.effective_user.id
    lang = get_lang(user_id)
    tx = T[lang]
    text, keyboard = await _px_packages_view(lang)
    if not keyboard:
        await update.message.reply_text(_s(tx["proxy_err"], ": No plans configured."))
        return
    await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")


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
                        + "\U0001f4b0 Price: " + fmt_usd(get_product_price_usd(p)) + "\n"
                        + "\U0001f4e6 Stock: " + str(get_product_stock(p)) + " available\n\n"
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
    application.add_handler(CommandHandler("proxies", proxies_command))
    application.add_handler(CommandHandler("admin", admin_command))
    application.add_handler(CallbackQueryHandler(callback_handler))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_message))
    print("Bot " + BOT_NAME + " is starting...")
    print("Web admin panel: http://localhost:5000")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
