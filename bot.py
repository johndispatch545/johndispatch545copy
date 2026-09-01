import os
import json
from typing import Dict, Optional
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

# ==================== DATA STORAGE ====================
ENABLED_GROUPS = {}
COMPANY_NAMES = {}
DRIVER_DATA = {}

# Conversation states
(
    ASK_COMPANY,
    ASK_FIRST_NAME,
    ASK_LAST_NAME,
    ASK_PHONE,
    ASK_EMAIL,
    ASK_LICENSE_NUMBER,
    ASK_LICENSE_STATE,
    ASK_TRUCK_NUMBER,
    ASK_TRUCK_YEAR,
    ASK_TRUCK_MAKE,
    ASK_TRUCK_MODEL,
    ASK_VIN,
    ASK_PLATE_NUMBER,
    ASK_PLATE_STATE,
    ASK_STATUS,
) = range(15)

# Status options for driver status field
STATUS_OPTIONS = ["Pick up", "TERMINATED", "RETURNED", "TRUCK CHANGE", "SHOP", "ACCIDENT"]

# Field definitions and order
FIELDS_ORDER = [
    "first_name",
    "last_name",
    "phone",
    "email",
    "license_number",
    "license_state",
    "truck_number",
    "truck_year",
    "truck_make",
    "truck_model",
    "vin",
    "plate_number",
    "plate_state",
    "status",
]

FIELD_PROMPTS = {
    "first_name": "Please enter the driver's first name:",
    "last_name": "Please enter the driver's last name:",
    "phone": "Please enter the driver's phone number:",
    "email": "Please enter the driver's email:",
    "license_number": "Please enter the driver's license number:",
    "license_state": "Please enter the license state (e.g., TX, OH):",
    "truck_number": "Please enter the truck/unit number:",
    "truck_year": "Please enter the truck year:",
    "truck_make": "Please enter the truck make (e.g., FRHT):",
    "truck_model": "Please enter the truck model/made (e.g., Cascadia):",
    "vin": "Please enter the VIN:",
    "plate_number": "Please enter the plate number:",
    "plate_state": "Please enter the plate state:",
    "status": "Please select the driver status:",
}


# ==================== COMMAND HANDLERS ====================

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /start command"""
    await update.message.reply_text(
        "🚚 Welcome to Driver Information Bot!\n\n"
        "Commands:\n"
        "/updadmin - Enable driver management in this group\n"
        "/newdriver - Add a new driver\n\n"
        "Use /updadmin first to enable this feature in your group!"
    )


async def updadmin_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /updadmin command - enable driver feature for the group"""
    if update.message.chat.type == "private":
        await update.message.reply_text("❌ This command can only be used in groups!")
        return

    group_id = update.message.chat.id
    group_name = update.message.chat.title

    # Enable the feature for this group
    ENABLED_GROUPS[group_id] = {
        "name": group_name,
        "enabled": True,
    }

    # Initialize storage for this group
    if group_id not in COMPANY_NAMES:
        COMPANY_NAMES[group_id] = []

    if group_id not in DRIVER_DATA:
        DRIVER_DATA[group_id] = {}

    await update.message.reply_text(
        f"✅ Driver Management enabled for {group_name}!\n\n"
        "Now use /newdriver to add a new driver."
    )


async def newdriver_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle /newdriver command - start driver information collection"""
    if update.message.chat.type == "private":
        await update.message.reply_text("❌ This command can only be used in groups!")
        return

    group_id = update.message.chat.id
    user_id = update.message.from_user.id

    # Check if feature is enabled for this group
    if group_id not in ENABLED_GROUPS or not ENABLED_GROUPS[group_id]["enabled"]:
        await update.message.reply_text(
            "❌ Driver management is not enabled for this group.\n"
            "Ask an admin to use /updadmin first."
        )
        return

    # Initialize driver data for this user
    if user_id not in DRIVER_DATA[group_id]:
        DRIVER_DATA[group_id][user_id] = {}

    # Start with company name selection
    await ask_company_name(update, context, group_id, user_id)


# ==================== COMPANY NAME HANDLERS ====================

async def ask_company_name(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    group_id: int, 
    user_id: int
) -> None:
    """Ask for company name with options"""
    saved_companies = COMPANY_NAMES.get(group_id, [])

    keyboard = []

    # Add saved companies as buttons
    for company in saved_companies:
        keyboard.append([InlineKeyboardButton(company, callback_data=f"company:{company}")])

    # Add "Add New Company Name" button
    keyboard.append([InlineKeyboardButton("➕ Add New Company Name", callback_data="company:new")])

    reply_markup = InlineKeyboardMarkup(keyboard)

    message = await update.message.reply_text(
        "Please select a Hired Company Name or add a new one:",
        reply_markup=reply_markup,
    )

    context.user_data[f"last_message_{group_id}_{user_id}"] = message.message_id


async def handle_company_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle company name selection"""
    query = update.callback_query
    await query.answer()

    group_id = query.message.chat.id
    user_id = query.from_user.id
    data = query.data

    if data == "company:new":
        # Ask for new company name
        msg = await query.edit_message_text("Please enter the new company name:")
        context.user_data[f"awaiting_new_company_{group_id}_{user_id}"] = True
        context.user_data[f"last_message_{group_id}_{user_id}"] = msg.message_id
    else:
        # Use selected company
        company_name = data.replace("company:", "")
        DRIVER_DATA[group_id][user_id]["company_name"] = company_name
        await query.delete_message()
        await ask_for_missing_field(update, context, group_id, user_id)


# ==================== FIELD HANDLING ====================

async def ask_for_missing_field(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    group_id: int, 
    user_id: int
) -> None:
    """Ask for the next missing field"""
    driver_data = DRIVER_DATA[group_id][user_id]

    # Find first missing field
    for field in FIELDS_ORDER:
        if field not in driver_data or driver_data[field] is None:
            await ask_field(update, context, group_id, user_id, field)
            return

    # All fields collected - show final template
    await show_final_template(update, context, group_id, user_id)


async def ask_field(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    group_id: int, 
    user_id: int, 
    field: str
) -> None:
    """Ask for a specific field"""
    context.user_data[f"awaiting_field_{group_id}_{user_id}"] = field

    if field == "status":
        # Show status options as buttons
        keyboard = [
            [InlineKeyboardButton(status, callback_data=f"status:{status}")]
            for status in STATUS_OPTIONS
        ]
        reply_markup = InlineKeyboardMarkup(keyboard)
        msg = await update.message.reply_text(FIELD_PROMPTS[field], reply_markup=reply_markup)
    else:
        msg = await update.message.reply_text(FIELD_PROMPTS[field])

    context.user_data[f"last_message_{group_id}_{user_id}"] = msg.message_id


async def handle_text_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle text input for driver information"""
    message = update.message
    group_id = message.chat.id
    user_id = message.from_user.id
    text = message.text.strip()

    # Only process if awaiting input
    is_awaiting_new_company = context.user_data.get(f"awaiting_new_company_{group_id}_{user_id}")
    current_field = context.user_data.get(f"awaiting_field_{group_id}_{user_id}")

    if not is_awaiting_new_company and not current_field:
        return

    # Check if awaiting new company name
    if is_awaiting_new_company:
        if group_id not in COMPANY_NAMES:
            COMPANY_NAMES[group_id] = []
        
        if text not in COMPANY_NAMES[group_id]:
            COMPANY_NAMES[group_id].append(text)

        DRIVER_DATA[group_id][user_id]["company_name"] = text
        context.user_data.pop(f"awaiting_new_company_{group_id}_{user_id}", None)

        # Delete previous message and continue
        try:
            last_msg_id = context.user_data.pop(f"last_message_{group_id}_{user_id}", None)
            if last_msg_id:
                await context.bot.delete_message(group_id, last_msg_id)
        except:
            pass

        await ask_for_missing_field(update, context, group_id, user_id)
        return

    # Handle field input
    if current_field:
        DRIVER_DATA[group_id][user_id][current_field] = text
        context.user_data.pop(f"awaiting_field_{group_id}_{user_id}", None)

        # Delete the question message
        try:
            last_msg_id = context.user_data.pop(f"last_message_{group_id}_{user_id}", None)
            if last_msg_id:
                await context.bot.delete_message(group_id, last_msg_id)
        except:
            pass

        # Ask for next field
        await ask_for_missing_field(update, context, group_id, user_id)


async def handle_status_selection(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handle status selection"""
    query = update.callback_query
    await query.answer()

    group_id = query.message.chat.id
    user_id = query.from_user.id
    status = query.data.replace("status:", "")

    DRIVER_DATA[group_id][user_id]["status"] = status
    context.user_data.pop(f"awaiting_field_{group_id}_{user_id}", None)

    await query.delete_message()

    # Ask for next field or show final template
    await ask_for_missing_field(update, context, group_id, user_id)


# ==================== TEMPLATE DISPLAY ====================

async def show_final_template(
    update: Update, 
    context: ContextTypes.DEFAULT_TYPE, 
    group_id: int, 
    user_id: int
) -> None:
    """Show the completed driver information template"""
    driver_data = DRIVER_DATA[group_id][user_id]

    # Build the final template with exact formatting
    template = (
        f"💁 Driver Name: {driver_data.get('first_name', '')} {driver_data.get('last_name', '')}\n"
        f"📰 Hired Company Name: {driver_data.get('company_name', '')}\n"
        f"👨 Driver Type: Company\n"
        f"Ph-nu# {driver_data.get('phone', '')}\n"
        f"E-mail: {driver_data.get('email', '')}\n"
        f"License# {driver_data.get('license_number', '')} ({driver_data.get('license_state', '')})\n"
        f"🚛 Truck Info:\n"
        f"Unit/Truck#: {driver_data.get('truck_number', '')}\n"
        f"Year: {driver_data.get('truck_year', '')}\n"
        f"Make: {driver_data.get('truck_make', '')}\n"
        f"Made/Model: {driver_data.get('truck_model', '')}\n"
        f"VIN: {driver_data.get('vin', '')}\n"
        f"Plate: {driver_data.get('plate_state', '')} / {driver_data.get('plate_number', '')}\n"
        f"📍 Status: {driver_data.get('status', '')}"
    )

    await update.message.reply_text(template)

    # Clear data for this user after completion
    DRIVER_DATA[group_id].pop(user_id, None)
    
    # Clean up context data
    for key in list(context.user_data.keys()):
        if f"{group_id}_{user_id}" in key:
            context.user_data.pop(key, None)


# ==================== MAIN APPLICATION ====================

async def main():
    """Start the bot"""
    TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

    if not TOKEN:
        print("❌ Error: TELEGRAM_BOT_TOKEN environment variable not set")
        return

    # Create application
    app = Application.builder().token(TOKEN).build()

    # Command handlers
    app.add_handler(CommandHandler("start", start_command))
    app.add_handler(CommandHandler("updadmin", updadmin_command))
    app.add_handler(CommandHandler("newdriver", newdriver_command))

    # Callback handlers for inline buttons
    app.add_handler(CallbackQueryHandler(handle_company_selection, pattern="^company:"))
    app.add_handler(CallbackQueryHandler(handle_status_selection, pattern="^status:"))

    # Message handler for text input
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text_input))

    # Start polling
    print("🚀 Bot started and running...")
    await app.run_polling()


if __name__ == "__main__":
    import asyncio
    asyncio.run(main())
