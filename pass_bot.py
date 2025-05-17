import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    ConversationHandler,
    InlineQueryHandler,
    CallbackQueryHandler,
    MessageHandler,
    ContextTypes,
    filters
)
import re
import os
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from datetime import datetime,timedelta
from collections import defaultdict
from ethiopian_date import EthiopianDateConverter

active_sessions = defaultdict(dict)
# Conversation states
(
    PERSONAL_FIRSTNAME,
    PERSONAL_MIDDLENAME,
    PERSONAL_LASTNAME,
    PERSONAL_GEZZ_FIRSTNAME,
    PERSONAL_GEZZ_MIDDLENAME,
    PERSONAL_GEZZ_LASTNAME,
    PERSONAL_BIRTHPLACE,
    PERSONAL_BIRTH_CERT_NO,
    PERSONAL_PHONE_NUMBER,
    PERSONAL_EMAIL,
    PERSONAL_HEIGHT,
    PERSONAL_DOB,
    PERSONAL_DONE,
    DROPDOWN_STATE 
) = range(6,20,1)
#address form states
(
    ADDRESS_REGION,
    ADDRESS_CITY,
    ADDRESS_STATE,
    ADDRESS_ZONE,
    ADDRESS_WOREDA,
    ADDRESS_KEBELE,
    ADDRESS_STREET,
    ADDRESS_HOUSE_NO,
    ADDRESS_PO_BOX,
    PAGE_QUANTITY_STATE,
) = range(20,30,1)
# File upload states
(
    FILE_UPLOAD_ID_DOC,
    FILE_UPLOAD_BIRTH_CERT ,
    PAYMENT_METHOD_STATE,
    SEND_CONFIRMATION_STATE,
    SEND_PAYMENT_INSTRUCTION

)= range(30, 35)
MAIN_MENU= 100
HELP_MENU = 1000
AFTER_START = 2000
# --- Dropdown Sequence Configuration ---
DROPDOWN_SEQUENCE = [ # Last number is buttons per row
    ('select[name="gender"]', "Gender", 2),
    ('select[name="martialStatus"]', "Marital Status", 3), # 1 means we'll use pagination
]

# Pagination configuration
OCCUPATION_PAGE_SIZE = 8  # Number of occupations per page
PAGINATION_PREFIX = "page_"  # Prefix for pagination callbacks
async def ask_region(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    message = update.message or update.callback_query.message
    await message.reply_text("Please select your region.")
    select_locator = page.locator("select.form-control").nth(0)
    await select_locator.wait_for()
    options = await select_locator.locator('option').all()
    valid_options = []
    
    for opt in options:
        value = await opt.get_attribute("value")
        text = (await opt.inner_text()).strip()
        if value and "--" not in text:
            valid_options.append((value, text))

    context.user_data["region_options"] = valid_options

    # Create keyboard with 2 buttons per row
    keyboard = []
    for i in range(0, len(valid_options), 3):
        row = []
        # Add first button of the pair
        if i < len(valid_options):
            value, text = valid_options[i]
            row.append(InlineKeyboardButton(text, callback_data=f"region_{value}"))
        # Add second button of the pair if exists
        if i+1 < len(valid_options):
            value, text = valid_options[i+1]
            row.append(InlineKeyboardButton(text, callback_data=f"region_{value}"))
        # Add third button of the pair if exists
        if i+2 < len(valid_options):
            value, text = valid_options[i+2]
            row.append(InlineKeyboardButton(text, callback_data=f"region_{value}"))
        keyboard.append(row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Please select a Region:", reply_markup=reply_markup)
    return 0

async def ask_region_response(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    query = update.callback_query
    await query.answer()
    
    selected_value = query.data.replace("region_", "")
    region_select = active_sessions[chat_id]['page'].locator("select.form-control").nth(0)
    await region_select.select_option(value=selected_value)
    
    
    # Manually trigger change event
    await active_sessions[chat_id]['page'].evaluate(
        """() => {
            const select = document.querySelectorAll("select.form-control")[0];
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }"""
    )
    region_name = next((text for value, text in context.user_data["region_options"] if value == selected_value), "Unknown")

    await query.edit_message_text(text=f"✅ Region selected: {region_name}!")
    context.user_data["selected_region"] = region_name
    return await ask_city(update, context)

async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    message = update.message or update.callback_query.message
    
    # Wait for the select element
    select_locator = page.locator("select.form-control").nth(1)
    await select_locator.wait_for()
    
    MAX_RETRIES = 10
    city_options = []
    
    for _ in range(MAX_RETRIES):
        await page.wait_for_timeout(500)
        city_options = await page.evaluate("""
                                () => {
                                    const select = document.querySelectorAll("select.form-control")[1];
                                    return Array.from(select.options)
                                        .filter(opt => {
                        const txt = opt.textContent.trim().toLowerCase();
                        return opt.value && txt !== "" && !txt.includes("select") && !txt.includes("--");
                    })
                                        .map(opt => [opt.value, opt.textContent.trim()]);
                                }
                            """)
        if city_options:
            break
    
    if not city_options:
        await message.reply_text("❌ Failed to load city options. Please try again.")
        return ConversationHandler.END

    # Save and show city options
    context.user_data["city_options"] = city_options
    
    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"city_{value}")] for value, text in city_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Please select a City:", reply_markup=reply_markup)
    
    return 1

async def ask_city_response(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    query = update.callback_query
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    await query.answer()
    
    selected_value = query.data.replace("city_", "")
    await active_sessions[chat_id]['page'].locator("select.form-control").nth(1).select_option(value=selected_value)
    city_name = next((text for value, text in context.user_data["city_options"] if value == selected_value), "Unknown")

    await query.edit_message_text(text=f"✅ City selected: {city_name}!")
    context.user_data["selected_city"] = city_name
    return await ask_office(update, context)

async def ask_office(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    
    select_locator = page.locator("select.form-control").nth(2)
    await select_locator.wait_for()
    
    MAX_RETRIES = 10
    office_options = []
    
    for _ in range(MAX_RETRIES):
        await page.wait_for_timeout(500)
        office_options = await page.evaluate("""
                            () => {
                                const select = document.querySelectorAll("select.form-control")[2];
                                return Array.from(select.options)
                                    .filter(opt => {
                    const txt = opt.textContent.trim().toLowerCase();
                    return opt.value && txt !== "" && !txt.includes("select") && !txt.includes("--");})
                                    .map(opt => [opt.value, opt.textContent.trim()]);
                            }
                        """)
        if office_options:
            break

    if not office_options:
        await message.reply_text("❌ Failed to load office options. Please try again.")
        return ConversationHandler.END

    context.user_data["office_options"] = office_options

    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"office_{value}")] for value, text in office_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Please select an Office:", reply_markup=reply_markup)

    return 2

async def ask_office_response(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    query = update.callback_query
    await query.answer()
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    selected_value = query.data.replace("office_", "")
    await active_sessions[chat_id]['page'].locator("select.form-control").nth(2).select_option(value=selected_value)
    office_name = next((text for value, text in context.user_data["office_options"] if value == selected_value), "Unknown")
    await query.edit_message_text(text=f"✅ Office selected: {office_name}!")
    return await ask_branch(update, context)

async def ask_branch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    select_locator = page.locator("select.form-control").nth(3)
    await select_locator.wait_for()

    MAX_RETRIES = 10
    branch_options = []

    for _ in range(MAX_RETRIES):
        await page.wait_for_timeout(500)
        branch_options = await page.evaluate("""
            () => {
                const select = document.querySelectorAll("select.form-control")[3];
                return Array.from(select.options)
                    .filter(opt => {
    const txt = opt.textContent.trim().toLowerCase();
    return opt.value && txt !== "" && !txt.includes("select") && !txt.includes("--");
                    })
                    .map(opt => [opt.value, opt.textContent.trim()]);
            }
        """)
        if branch_options:
            break

    if not branch_options:
        await message.reply_text("❌ Failed to load branch options. Please try again.")
        return ConversationHandler.END

    context.user_data["branch_options"] = branch_options

    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"branch_{value}")] for value, text in branch_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Please select a Branch:", reply_markup=reply_markup)

    return 3

async def ask_branch_response(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    message = update.message or update.callback_query.message
    query = update.callback_query
    await query.answer()
    
    selected_value = query.data.replace("branch_", "")
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    await active_sessions[chat_id]['page'].locator("select.form-control").nth(3).select_option(value=selected_value)
    branch_name = next((text for value, text in context.user_data["branch_options"] if value == selected_value), "Unknown")
    await query.edit_message_text(text=f"✅ Branch selected: {branch_name}!")
    
    await page.get_by_role("button", name="Next").click()
    status_msg = await message.reply_text("Checking available dates... from current month...")
    await page.wait_for_timeout(3000)
    await status_msg.edit_text("almost there...checking available dates...")
    return await ask_date(update, context, status_msg)

async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE,status_msg) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    status_msg = status_msg 
    await status_msg.edit_text("Checking available dates...please wait")
    page = active_sessions[chat_id]['page']
    calendar_visible = await page.locator("div.react-calendar__month-view__days").is_visible()
    if not calendar_visible:
        await message.reply_text("Sorry, we couldn't find any available dates. Please try again later.")
        await cancel(update, context)
        return ConversationHandler.END
    await status_msg.edit_text("Calendar is visible, checking for available dates...")
    # Wait for available dates
    while True:
        day_buttons = await page.locator("div.react-calendar__month-view__days button:not([disabled])").all()
        await status_msg.edit_text(f"Found {len(day_buttons)} available dates.")
        if day_buttons:
            break
        await page.locator("button.react-calendar__navigation__next-button").click()
        await page.wait_for_timeout(1000)
    # Extract available dates
    await status_msg.edit_text("Extracting available dates...")
    available_days = []
    for i, button in enumerate(day_buttons, start=1):
        label = await button.locator("abbr").get_attribute("aria-label")
        if label:
            available_days.append((i, label, button))

    context.user_data["available_days"] = available_days

    # Create inline keyboard for dates
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"date_{i}")] for i, label, _ in available_days
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await status_msg.edit_text("📅 Available Dates:", reply_markup=reply_markup)

    return 4

async def ask_date_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    selected_idx = int(query.data.replace("date_", ""))
    available_days = context.user_data["available_days"]
    
    for i, label, button in available_days:
        if i == selected_idx:
            await button.click()
            await query.edit_message_text(text=f"✅ Selected date: {label}")
            break

    await active_sessions[chat_id]['page'].wait_for_timeout(1000)
    return await handle_time_slot(update, context)

async def handle_time_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    page = active_sessions[update.effective_chat.id]['page']
    message = update.message or update.callback_query.message
    status_msg = await message.reply_text("Checking for available time slots...")
    # Check both slot types simultaneously
    morning_buttons = await page.locator("table#displayMorningAppts input.btn_select").all()
    afternoon_buttons = await page.locator("table#displayAfternoonAppts input.btn_select").all()
  
    if not morning_buttons and not afternoon_buttons:
        await status_msg.edit_text("❌ No time slots available.")
        return await ask_date(update, context, status_msg)
    if morning_buttons:
        await status_msg.edit_text("🕒Morning slots available.")
        await morning_buttons[0].click()
        await status_msg.edit_text("🕒 Morning time slot selected.")
    elif afternoon_buttons:
        await status_msg.edit_text("🕒Afternoon slots available.")
        await afternoon_buttons[0].click()
        await status_msg.edit_text("🕒 Afternoon time slot selected.")
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']

    await page.get_by_role("button", name="Next").click()
    await page.wait_for_timeout(1000)
    return await ask_first_name(update, context)

# --- Ask Functions ---
async def ask_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    await message.reply_text("Enter your First Name:")
    return PERSONAL_FIRSTNAME

async def handle_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["first_name"] = message.text.strip()
    await message.reply_text("Enter your Middle Name:")
    return PERSONAL_MIDDLENAME

async def handle_middle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["middle_name"] = message.text.strip()
    await message.reply_text("Enter your Last Name:")
    return PERSONAL_LASTNAME

async def handle_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["last_name"] = message.text.strip()
    await message.reply_text("Enter your First Name in Amharic:")
    return PERSONAL_GEZZ_FIRSTNAME

async def handle_gez_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["amharic_first_name"] = message.text.strip()
    await message.reply_text("Enter your Middle Name in Amharic:")
    return PERSONAL_GEZZ_MIDDLENAME

async def handle_gez_middle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["amharic_middle_name"] = message.text.strip()
    await message.reply_text("Enter your Last Name in Amharic:")
    return PERSONAL_GEZZ_LASTNAME

async def handle_gez_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["amharic_last_name"] = message.text.strip()
    await message.reply_text("Enter your Birth Place:")
    return PERSONAL_BIRTHPLACE

async def handle_birth_place(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    context.user_data["birth_place"] = message.text.strip()
    await message.reply_text(" Enter your Phone Number:\n"
        "• Format: 0912345678 or 0712345678\n"
        "• Ethiopian phone numbers should start with 09 or 07.\n"
        "• Please enter a valid 10-digit number."
    )
    return PERSONAL_PHONE_NUMBER

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    phone_number = message.text.strip()
    cleaned_number = ''.join(filter(str.isdigit, phone_number))
    
    # Ethiopian phone number validation
    if (len(cleaned_number) == 10 and 
        cleaned_number.startswith(('09', '07')) and
        cleaned_number[2:].isdigit()):
        
        context.user_data["phone_number"] = cleaned_number
        await message.reply_text(
        "Enter your Date of Birth:\n"
        "• Format: mm/dd/yyyy(Gregorian)\n"
        "• Or use Ethiopian date: yyyy/mm/dd (e.g., 2015/03/12)"
    )   
        return PERSONAL_DOB
    
    # If validation fails
    await message.reply_text(
        "❌ Invalid Ethiopian phone number. Please enter a 10-digit number starting with 09 or 07.\n"
        "Example: 0912345678 or 0712345678"
    )
    return PERSONAL_PHONE_NUMBER

def validate_gregorian_date(date_str):
    """Validate Gregorian date in either mm/dd/yyyy or mmddyyyy format"""
    try:
        # Try to parse both formats
        if '/' in date_str:
            print("Detected mm/dd/yyyy format.")
            date_obj = datetime.strptime(date_str, "%m/%d/%Y")
        else:
            if len(date_str) != 8:
                print("Invalid date length for mmddyyyy format.")
                return False
            date_obj = datetime.strptime(date_str, "%m%d%Y")
        
        # Additional sanity checks
        if date_obj.year < 1900 or date_obj.year > datetime.now().year:
            print("Year out of valid range")
            return False
        return date_obj
    except ValueError:
        print("Invalid date format")
        return False

def convert_ethiopian_to_gregorian(eth_date_str):
    """Convert Ethiopian date (YYYY/MM/DD) to Gregorian"""
    try:
        # Basic format validation
        if not re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', eth_date_str):
            print("Invalid Ethiopian date format")
            return False
            
        year, month, day = map(int, eth_date_str.split('/'))
        
        # Ethiopian date validation
        if month < 1 or month > 13 or day < 1 or day > 30:
            print("Invalid Ethiopian date values")
            return False
        if month == 13 and day > 5:  # Pagume has only 5 or 6 days
            print("Invalid Ethiopian date for Pagume")
            return False
            
        greg_date = EthiopianDateConverter.to_gregorian(year, month, day)
        
        # Final sanity check
        if greg_date.year < 1900 or greg_date > datetime.now().date():
            print("Converted date is out of valid range")
            return False
            
        return greg_date

    except Exception as e:
        print(f"Error converting Ethiopian date: {e}")
        return False

async def handle_dob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    dob_input = message.text.strip()
    
    # Check for Ethiopian date (contains Ethiopic numbers or Amharic)
    if re.search(r'[ሀ-ፕ]|[\u1369-\u137C]', dob_input):
        await message.reply_text("Please enter the date in English numbers (0-9)")
        return PERSONAL_DOB
    # Try Ethiopian format (YYYY/MM/DD)
    if '/' in dob_input and (dob_input.count('/') == 2 and re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', dob_input)):
        print("Ethiopian date format detected.")
        greg_date = convert_ethiopian_to_gregorian(dob_input)
        if greg_date:
            context.user_data["dob"] = greg_date.strftime("%m/%d/%Y")
            await message.reply_text(f"Converted to Gregorian: {context.user_data['dob']}")
            return await ask_dropdown_option(update,context)
    
    # Try Gregorian formats
    date_obj = validate_gregorian_date(dob_input)
    print(f"Gregorian date validation result: {date_obj}")
    if date_obj:
        context.user_data["dob"] = date_obj.strftime("%m/%d/%Y")
        return await ask_dropdown_option(update,context)
    
    # If all validations fail
    await message.reply_text(
        "❌ Invalid date format. Please enter:\n"
        "• Ethiopian: YYYY/MM/DD (e.g., 2012/09/12)\n"
        "• Gregorian: mm/dd/yyyy (e.g., 05/21/1990)\n"
        "• Month (1-12), Day (1-31), Year (1900-now)"
    )
    return PERSONAL_DOB

async def ask_dropdown_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    step = context.user_data.get("dropdown_step", 0)
    
    if step >= len(DROPDOWN_SEQUENCE):
        return await fill_personal_form_on_page(update, context)

    selector, label, buttons_per_row = DROPDOWN_SEQUENCE[step]
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    dropdown = page.locator(selector)
    await dropdown.wait_for()
    options = await dropdown.locator('option').all()

    valid_options = []
    for opt in options:
        value = await opt.get_attribute("value")
        text = (await opt.inner_text()).strip()
        if value and "--" not in text:
            valid_options.append((value, text))

    context.user_data["dropdown_options"] = valid_options
    context.user_data["current_dropdown_selector"] = selector

    # Special handling for occupation with pagination
    if label == "Occupation":
        return await show_occupation_page(update, context, valid_options, 0)

    # Create inline keyboard with specified buttons per row
    keyboard = []
    row = []
    for i, (value, text) in enumerate(valid_options, 1):
        row.append(InlineKeyboardButton(text, callback_data=f"dropdown_{step}_{value}"))
        if i % buttons_per_row == 0 or i == len(valid_options):
            keyboard.append(row)
            row = []

    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(f"Please select {label}:", reply_markup=reply_markup)

    return DROPDOWN_STATE

async def show_occupation_page(update: Update, context: ContextTypes.DEFAULT_TYPE, options: list, page_num: int) -> int:
    message = update.message or update.callback_query.message
    start_idx = page_num * OCCUPATION_PAGE_SIZE
    end_idx = start_idx + OCCUPATION_PAGE_SIZE
    page_options = options[start_idx:end_idx]

    keyboard = []
    # Add occupation buttons (2 per row)
    for i in range(0, len(page_options), 2):
        row = []
        if i < len(page_options):
            value, text = page_options[i]
            row.append(InlineKeyboardButton(text, callback_data=f"dropdown_4_{value}"))  # 4 is the step for occupation
        if i+1 < len(page_options):
            value, text = page_options[i+1]
            row.append(InlineKeyboardButton(text, callback_data=f"dropdown_4_{value}"))
        if row:
            keyboard.append(row)

    # Add pagination controls if needed
    pagination_row = []
    if page_num > 0:
        pagination_row.append(InlineKeyboardButton("⬅️ Previous", callback_data=f"{PAGINATION_PREFIX}occupation_{page_num-1}"))
    if end_idx < len(options):
        pagination_row.append(InlineKeyboardButton("Next ➡️", callback_data=f"{PAGINATION_PREFIX}occupation_{page_num+1}"))
    if pagination_row:
        keyboard.append(pagination_row)

    reply_markup = InlineKeyboardMarkup(keyboard)
    
    if update.callback_query:
        await update.callback_query.edit_message_text(
            text="Please select your Occupation:",
            reply_markup=reply_markup
        )
    else:
        await message.reply_text("Please select your Occupation:", reply_markup=reply_markup)
    
    return DROPDOWN_STATE

async def handle_dropdown_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    message = update.message or update.callback_query.message
    await query.answer()
    
    # Handle pagination
    if query.data.startswith(PAGINATION_PREFIX):
        _, category, page_num = query.data.split("_")
        page_num = int(page_num)
        options = context.user_data.get("dropdown_options", [])
        return await show_occupation_page(update, context, options, page_num)
    
    # Handle normal dropdown selection
    _, step, value = query.data.split("_")
    step = int(step)
    options = context.user_data.get("dropdown_options", [])
    selector = context.user_data.get("current_dropdown_selector")

    # Find the selected option
    selected_option = next((opt for opt in options if opt[0] == value), None)
    if not selected_option:
        await query.edit_message_text(text="❌ Invalid selection. Please try again.")
        return DROPDOWN_STATE

    value, label = selected_option
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    await page.select_option(selector, value)
    await query.edit_message_text(text=f"✅ {label} selected.")

    # Move to next step
    context.user_data["dropdown_step"] = step + 1
    return await ask_dropdown_option(update, context)
    
# --- Final Form Filling on Page ---
async def fill_personal_form_on_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    user_data = context.user_data
    await page.fill('input[name="firstName"]', user_data["first_name"])
    await page.fill('input[name="middleName"]', user_data["middle_name"])
    await page.fill('input[name="lastName"]', user_data["last_name"])
    await page.fill('#date-picker-dialog', '')
    await page.type('#date-picker-dialog', user_data["dob"])
    await page.fill('input[name="geezFirstName"]', user_data["amharic_first_name"])
    await page.fill('input[name="geezMiddleName"]', user_data["amharic_middle_name"])
    await page.fill('input[name="geezLastName"]', user_data["amharic_last_name"])
    await page.select_option('select[name="nationalityId"]', "ETHIOPIA")   
    await page.fill('input[name="phoneNumber"]', user_data["phone_number"])
    #await page.fill('input[name="email"]', user_data["email"])
    await page.fill('input[name="birthPlace"]', user_data["birth_place"])
    #await page.fill('input[name="birthCertificatNo"]', user_data["birth_cert_no"])
    #await page.fill('input[name="height"]', user_data["height"])

    await page.get_by_role("button", name="Next").click()
    await page.wait_for_selector('select[name="region"]')
    region_select = page.locator("select[name='region']")
    selected_region = context.user_data["selected_region"]
    await region_select.select_option(value=selected_region)

    return await fill_address_form_on_page(update, context)


async def fill_address_form_on_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    user_data = context.user_data
    await page.fill('input[name="city"]', user_data["selected_city"])
    # Click Next buttons
    await page.get_by_role("button", name="Next").click()
    await page.get_by_role("button", name="Next").click()
    await page.get_by_role("button", name="Submit").click()

    return await file_upload_from_telegram(update, context)

async def file_upload_from_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    keyboard = [
        [InlineKeyboardButton("📤 Upload ID Document", callback_data="upload_id")],
        [InlineKeyboardButton("📤 Upload Birth Certificate", callback_data="upload_birth")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        "📤 Please upload your documents:",
        reply_markup=reply_markup
    )
    return FILE_UPLOAD_ID_DOC
async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    ALLOWED_EXTENSIONS = {'jpeg', 'jpg', 'png', 'gif', 'pdf'}
    MAX_FILE_SIZE_MB = 1
    
    if update.callback_query:
        # Handle button selection
        query = update.callback_query
        await query.answer()
        
        if query.data == "upload_id":
            context.user_data["current_file_type"] = "id_doc"
            await query.edit_message_text(text="Please upload your **Valid Resident/Gov Employee ID** (JPEG, PNG, PDF, <1MB).")
            return FILE_UPLOAD_ID_DOC
        elif query.data == "upload_birth":
            context.user_data["current_file_type"] = "birth_cert"
            await query.edit_message_text(text="Please upload your **Authenticated Birth Certificate** (JPEG, PNG, PDF, <1MB).")
            return FILE_UPLOAD_BIRTH_CERT
    
    # Handle actual file upload
    file = message.document or (message.photo[-1] if message.photo else None)

    if not file:
        await message.reply_text("❌ Please send a file (image or document).")
        return FILE_UPLOAD_ID_DOC if context.user_data["current_file_type"] == "id_doc" else FILE_UPLOAD_BIRTH_CERT

    if hasattr(file, "file_name"):
        ext = file.file_name.split('.')[-1].lower()
    else:
        ext = "jpg"  # for photo

    if ext not in ALLOWED_EXTENSIONS:
        await message.reply_text("❌ Unsupported file type. Use JPEG, PNG, PDF, etc.")
        return FILE_UPLOAD_ID_DOC if context.user_data["current_file_type"] == "id_doc" else FILE_UPLOAD_BIRTH_CERT

    if file.file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        await message.reply_text("❌ File too large. Must be less than 1MB.")
        return FILE_UPLOAD_ID_DOC if context.user_data["current_file_type"] == "id_doc" else FILE_UPLOAD_BIRTH_CERT

    file_path = f"downloads/{context.user_data['current_file_type']}.{ext}"
    tg_file = await file.get_file()
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    await tg_file.download_to_drive(file_path)

    context.user_data[context.user_data["current_file_type"]] = file_path

    if context.user_data["current_file_type"] == "id_doc":
        keyboard = [[InlineKeyboardButton("📤 Upload Birth Certificate", callback_data="upload_birth")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        await message.reply_text("✅ ID uploaded. Please upload your birth certificate:", reply_markup=reply_markup)
        return FILE_UPLOAD_BIRTH_CERT

    await message.reply_text("✅ All files received. Uploading to the form...")
    return await upload_files_to_form(update, context)

async def upload_files_to_form(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    await page.set_input_files('input[name="input-0"]', context.user_data["id_doc"])
    await page.set_input_files('input[name="input-1"]', context.user_data["birth_cert"])
    await page.get_by_role("button", name="Upload").click()
    await message.reply_text("📁 Uploaded successfully.")

    await page.click('label[for="defaultUnchecked"]')
    await page.get_by_role("button", name="Next").click()

    # Next step
    return await ask_payment_method(update, context)

async def ask_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    methods = ["CBE Birr", "TELE Birr", "CBE Mobile"]
    context.user_data["payment_methods"] = methods

    keyboard = [
        [InlineKeyboardButton(method, callback_data=f"payment_{i}")] 
        for i, method in enumerate(methods)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        "💳 Please select your payment method:",
        reply_markup=reply_markup
    )
    return PAYMENT_METHOD_STATE

async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    message = update.message or update.callback_query.message
    await query.answer()
    
    selected_idx = int(query.data.replace("payment_", ""))
    methods = context.user_data["payment_methods"]
    selected_method = methods[selected_idx]
    
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    await page.locator(f"div.type:has(p:has-text('{selected_method}')) p").click()
    await page.click('label[for="defaultUncheckedDisabled2"]')
    await page.get_by_role("button", name="Next").click()

    await query.edit_message_text(text=f"✅ Selected payment method: {selected_method}")
    return await generate_complete_output(update, context)

async def generate_complete_output(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    status_msg = await message.reply_text("Extracting application data....")
    page = active_sessions[chat_id]['page']
    await page.wait_for_load_state("networkidle")
    await page.wait_for_selector('div.col-md-4.order-md-2.mb-4.mt-5')

    content = await page.content()
    soup = BeautifulSoup(content, 'html.parser')
    containers = soup.select('div.col-md-4.order-md-2.mb-4.mt-5 ul.list-group.mb-3')

    data = {}
    for container in containers:
        items = container.find_all('li', class_='list-group-item')
        for item in items[1:]:  # Skip the title row
            left = item.find('h6')
            right = item.find('span') or item.find('strong')
            await status_msg.edit_text("Extracting application data.... PLEASE WAIT")
            if left and right:
                await status_msg.edit_text("Extracting application data....")
                key = left.get_text(strip=True)
                value = right.get_text(strip=True)
                data[key] = value
    await status_msg.edit_text("All data extracted successfully.")
    # Format the message
    message_t = "📄 *Your ePassport Summary:*\n\n"
    for key, value in data.items():
        message_t += f"*{key}:* {value}\n"

    await status_msg.edit_text(message_t, parse_mode="Markdown")

    # Extract Application Number and use as filename (sanitize it)
    app_number = data.get("Application Number", None).replace(" ", "_")
    filename = f"{app_number}.pdf"

    return await save_pdf(update, context, page, filename=filename,app_number=app_number)

async def save_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE, page, filename="output.pdf", app_number=None) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    status_msg = await message.reply_text("Saving PDF...")
    page = active_sessions[chat_id]['page']
    folder = "filesdownloaded"
    os.makedirs(folder, exist_ok=True)
    # Save the PDF
    pdf_path = os.path.join(folder, filename)
    await page.pdf(path=pdf_path)
    print(f"📄 PDF saved as {pdf_path}")
    await status_msg.edit_text("📎 Uploading PDF ...")
    # Send PDF to user
    with open(pdf_path, "rb") as pdf_file:
        await message.reply_document(document=pdf_file, filename=filename, caption="📎 Here is your instruction PDF.")
        result= await main_passport_status(update, context,page,app_number)
        if result:
            await message.reply_text(result)

        with open(f"Passport_status_{app_number}.pdf", "rb") as pdf_file:
            await message.reply_document(pdf_file, caption="Your Appointment report is ready.")
    await message.reply_text("✅ All done!")
    await message.reply_text("Thank you for using the Ethiopian Passport Booking Bot!")
    await message.reply_text("If you need further assistance, please contact support.")
    return await new_or_check(update, context)
async def new_or_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    await page.click('a[href="/request-appointment"]')
    await page.wait_for_selector("label[for='defaultChecked2']", timeout=10000)
    await page.click("label[for='defaultChecked2']")
    await page.click(".card--link")
    await message.reply_text(
        "Please choose an option:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 new  Appointment", callback_data="new_appointment")],
            [InlineKeyboardButton("🔍 Check Passport Status", callback_data="passport_status")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
        ])
    )

    return AFTER_START

async def after_start(update:Update,context:ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    query = update.callback_query
    await query.answer()
    
    if query.data == "new_appointment":
        return await new_appointment(update, context)
    elif query.data == "passport_status":
        return await ask_application_number(update, context)
    elif query.data == "help":
        return await help(update, context)
    else:
        await message.reply_text("❌ Invalid option, please try again.")
        return AFTER_START


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    status_msg = await message.reply_text("Initializing session...")
    # Close existing session if any
    if chat_id in active_sessions:
        if 'page' in active_sessions[chat_id]:
            await active_sessions[chat_id]['page'].close()
        if 'browser' in active_sessions[chat_id]:
            await active_sessions[chat_id]['browser'].close()
        if 'playwright' in active_sessions[chat_id]:
            await active_sessions[chat_id]['playwright'].stop()
        del active_sessions[chat_id]
    
    # Setup new browser session for this user
    try:
        playwright = await async_playwright().start()
        await status_msg.edit_text("⚡Launching browser...")
        browser = await playwright.chromium.launch(headless=True)
        browser_context = await browser.new_context()
        page = await browser_context.new_page()
        await page.goto("https://www.ethiopianpassportservices.gov.et/request-appointment", wait_until="domcontentloaded")
        await status_msg.edit_text("⚡Browser launched. Please wait...")
        await status_msg.edit_text("⚡Loading page...")
        # Store the session
        active_sessions[chat_id] = {
            'playwright': playwright,
            'browser': browser,
            'page': page,
            'last_active': datetime.now()
        }
        await status_msg.edit_text("⚡Page loaded. Please wait...")
        # Initialize user data
        context.user_data.clear()
        
        
        await status_msg.edit_text("Welcome to the Ethiopian Passport Booking Bot!")
        await message.reply_text(
            "Please choose an option:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📅 Book Appointment", callback_data="book_appointment")],
                [InlineKeyboardButton("🔍 Check Passport Status", callback_data="passport_status")],
                [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
            ])
        )

        await page.wait_for_selector("label[for='defaultChecked2']", timeout=10000)
        await page.click("label[for='defaultChecked2']")
        await page.click(".card--link")
        return MAIN_MENU
    except Exception as e:
        await message.reply_text(f"❌ Error initializing session: {str(e)}")
        return ConversationHandler.END

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    chat_id = query.message.chat.id
    
    # Update last active time
    if chat_id in active_sessions:
        active_sessions[chat_id]['last_active'] = datetime.now()
    
    if query.data == "book_appointment":
        await query.edit_message_text(text="📅 Booking an appointment...")
        return await new_appointment(update, context)
    elif query.data == "passport_status":
        await query.edit_message_text(text="🔍 Checking passport status...")
        return await ask_application_number(update, context)
    elif query.data == "help":
        return await help(update, context)
    else:   
        await query.edit_message_text(text="❌ Invalid option, please try again.")

async def new_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    
    if chat_id not in active_sessions:
        await message.reply_text("❌ Session expired. Please /start again.")
        return ConversationHandler.END
    
    try:
        page = active_sessions[chat_id]['page']
        active_sessions[chat_id]['last_active'] = datetime.now()
        


        await page.wait_for_load_state("load")
        await page.click(".card--teal.flex.flex--column")
        
        await message.reply_text("✅ Ready! Let's begin your appointment booking.")
        return await ask_region(update, context)
    except Exception as e:
        await message.reply_text(f"❌ Error starting appointment: {str(e)}")
        return await main_menu_handler(update, context)


async def main_passport_status(update: Update, context: ContextTypes.DEFAULT_TYPE, page, application_number) -> str:
        message = update.message or update.callback_query.message
        status_msg = await message.reply_text("Loading status page...")
        await page.click('a[href="/Status"]')
        await status_msg.edit_text("⚡Page loaded. Please wait...")
        await page.wait_for_selector('input[placeholder="Application Number"]', timeout=5000)
        await status_msg.edit_text("Filling application number...")
        await page.fill('input[placeholder="Application Number"]', application_number)
        await status_msg.edit_text("checking data...")

        # Click the search button using its text and class
        await page.click('button:has-text("Search")')
        if await page.locator('h5.text-danger.text-center').is_visible():
            await status_msg.edit_text("❌ Invalid Application Number. Please try again.")
            return "❌ Invalid Application Number. Please try again."   
        await page.wait_for_selector('a.card--link', timeout=50000)
        card = await page.query_selector('a.card--link')
        text_content = await card.inner_text()
        eye_button = await card.query_selector('div i.fa-eye')
        if eye_button:
            await eye_button.click()
        else:
            print("❌ 'Eye' icon not found.")

        await page.wait_for_timeout(3000)
        await status_msg.edit_text("Generating PDF...")
        await generate_official_pdf(page, application_number)
        await status_msg.edit_text("PDF generated successfully.")
        return text_content.strip()

async def generate_official_pdf(page, application_number):
    await page.pdf(
        path=f"Passport_status_{application_number}.pdf",
        print_background=True, )

async def ask_application_number(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    message = update.message or update.callback_query.message
    await message.reply_text("Please enter your Application Number to get started.")
    return 1

async def passport_status(update: Update, context: ContextTypes.DEFAULT_TYPE)-> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    passport_number = message.text
    result= await main_passport_status(update, context, page, passport_number)
    if result:
        await message.reply_text(result)
        with open(f"Passport_status_{passport_number}.pdf", "rb") as pdf_file:
            await message.reply_document(pdf_file, caption="Your passport status report is ready.")
            await message.reply_text("✅ All done!")
    return await new_or_check(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    
    # Clean up browser session
    if chat_id in active_sessions:
        if 'page' in active_sessions[chat_id]:
            await active_sessions[chat_id]['page'].close()
        if 'browser' in active_sessions[chat_id]:
            await active_sessions[chat_id]['browser'].close()
        if 'playwright' in active_sessions[chat_id]:
            await active_sessions[chat_id]['playwright'].stop()
        del active_sessions[chat_id]
    # Clear user data
    context.user_data.clear()
    
    await message.reply_text("❌ Operation cancelled. ,Starting over...")
    await start(update, context)
    return ConversationHandler.END

async def help(update:Update,context:ContextTypes.DEFAULT_TYPE)->int:
    message = update.message or update.callback_query.message
    keyboard = [
        [InlineKeyboardButton("Book Appointment", callback_data="help_book")],
        [InlineKeyboardButton("Check Status", callback_data="help_status")],
        [InlineKeyboardButton("Cancel Appointment", callback_data="help_cancel")],
        [InlineKeyboardButton("Contact Support", callback_data="help_contact")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text(
        "I can help you with the following:",
        reply_markup=reply_markup
    )
    return HELP_MENU

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    await query.answer()
    
    if query.data == "help_book":
        await query.edit_message_text(text="To book an appointment, use the /new_appointment command.\n\nFollow the prompts to select your region, city, and other details.\n\nplease make sure to have your documents ready.")
    elif query.data == "help_status":
        await query.edit_message_text(text="To check your passport status, use the /passport_status command. \n\nEnter your application number when prompted.")
    elif query.data == "help_cancel":
        await query.edit_message_text(text="To cancel your appointment, use the /cancel command. \n\nThis will clear your current session and start over.")
    elif query.data == "help_contact":
        await query.edit_message_text(text="For support, please contact us at t.me/ns_asharama")
    return ConversationHandler.END
async def cleanup_inactive_sessions():
    while True:
        try:
            now = datetime.now()
            for chat_id in list(active_sessions.keys()):
                try:
                    last_active = active_sessions[chat_id].get('last_active')
                    if last_active and now - last_active > timedelta(minutes=30):
                        # Cleanup inactive session
                        if 'page' in active_sessions[chat_id]:
                            await active_sessions[chat_id]['page'].close()
                        if 'browser' in active_sessions[chat_id]:
                            await active_sessions[chat_id]['browser'].close()
                        if 'playwright' in active_sessions[chat_id]:
                            await active_sessions[chat_id]['playwright'].stop()
                        del active_sessions[chat_id]
                except Exception as e:
                    print(f"Error cleaning up session for {chat_id}: {e}")
            await asyncio.sleep(300)  # Check every 5 minutes
        except asyncio.CancelledError:
            break
        except Exception as e:
            print(f"Error in cleanup task: {e}")
            await asyncio.sleep(60)  # Wait before retrying

if __name__ == "__main__":
    # Create application
    application = Application.builder() \
    .token("8076860650:AAEprRHsyLQFya7gZjQItySYtEyHHX8UsV8") \
    .read_timeout(30) \
    .write_timeout(30) \
    .connect_timeout(30) \
    .pool_timeout(30) \
    .build()
    #Main menu handler
    main_menu = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_handler)],
            AFTER_START: [
                CallbackQueryHandler(after_start, pattern="^new_appointment"),
                CallbackQueryHandler(after_start, pattern="^passport_status"),
                CallbackQueryHandler(after_start, pattern="^help")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,  # Keep this as False since we have mixed handlers
        per_user=True,
        per_chat=True,
        )

    # Status check handler
    check_status = ConversationHandler(
        entry_points=[
            CommandHandler("passport_status", ask_application_number),
            CallbackQueryHandler(ask_application_number, pattern="^passport_status")
        ],
        states={
            1: [MessageHandler(filters.TEXT & ~filters.COMMAND, passport_status)],
            AFTER_START: [
                CallbackQueryHandler(after_start, pattern="^new_appointment"),
                CallbackQueryHandler(after_start, pattern="^passport_status"),
                CallbackQueryHandler(after_start, pattern="^help")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,  # Keep this as False since we have mixed handlers
        per_user=True,
        per_chat=True,
    )
    
    # Main form handler
    form_handle = ConversationHandler(
        entry_points=[CommandHandler("new_appointment", new_appointment),
                    CallbackQueryHandler(new_appointment, pattern="^book_appointment")],
        states={
            # Your state handlers...
            AFTER_START: [
                CallbackQueryHandler(after_start, pattern="^new_appointment"),
                CallbackQueryHandler(after_start, pattern="^passport_status"),
                CallbackQueryHandler(after_start, pattern="^help")
            ],
            0: [CallbackQueryHandler(ask_region_response, pattern="^region_")],
            1: [CallbackQueryHandler(ask_city_response, pattern="^city_")],
            2: [CallbackQueryHandler(ask_office_response, pattern="^office_")],
            3: [CallbackQueryHandler(ask_branch_response, pattern="^branch_")],
            4: [CallbackQueryHandler(ask_date_response, pattern="^date_")],
            # Message handlers
            PERSONAL_FIRSTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_first_name)],
            PERSONAL_MIDDLENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_middle_name)],
            PERSONAL_LASTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_last_name)],
            PERSONAL_GEZZ_FIRSTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gez_first_name)],
            PERSONAL_GEZZ_MIDDLENAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gez_middle_name)],
            PERSONAL_GEZZ_LASTNAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_gez_last_name)],
            PERSONAL_BIRTHPLACE: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_birth_place)],
            PERSONAL_PHONE_NUMBER: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_phone_number)],
            PERSONAL_DOB: [MessageHandler(filters.TEXT & ~filters.COMMAND, handle_dob)],
            DROPDOWN_STATE: [
                CallbackQueryHandler(handle_dropdown_response, pattern="^dropdown_"),
                CallbackQueryHandler(handle_dropdown_response, pattern=f"^{PAGINATION_PREFIX}"),
            ],
            FILE_UPLOAD_ID_DOC: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file_upload),
                CallbackQueryHandler(handle_file_upload, pattern="^upload_")
            ],
            FILE_UPLOAD_BIRTH_CERT: [
                MessageHandler(filters.Document.ALL | filters.PHOTO, handle_file_upload),
                CallbackQueryHandler(handle_file_upload, pattern="^upload_")
            ],
            PAYMENT_METHOD_STATE: [CallbackQueryHandler(handle_payment_method, pattern="^payment_")],
            AFTER_START: [
                CallbackQueryHandler(after_start, pattern="^new_appointment"),
                CallbackQueryHandler(after_start, pattern="^passport_status"),
                CallbackQueryHandler(after_start, pattern="^help")
            ],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,  # Keep this as False since we have mixed handlers
        per_user=True,
        per_chat=True,
    )

    #help handler
    help_h= ConversationHandler(
        entry_points=[
            CommandHandler("help", help),
            CallbackQueryHandler(help, pattern="^help")
        ],
        states={
            HELP_MENU: [CallbackQueryHandler(handle_help, pattern="^help_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    # Add handlers
    application.add_handler(CommandHandler("start" , start))
    application.add_handler(form_handle)
    application.add_handler(check_status)
    application.add_handler(help_h)
    application.add_handler(CommandHandler("cancel", cancel))
    async def post_init(application):
        asyncio.create_task(cleanup_inactive_sessions())

    application.post_init = post_init
    application.run_polling()