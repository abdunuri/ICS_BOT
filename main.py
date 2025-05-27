import asyncio
import logging
import os
from datetime import datetime, timedelta
from collections import defaultdict
import re
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
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
from ethiopian_date import EthiopianDateConverter
import dotenv

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler('passport_bot.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

dotenv.load_dotenv()
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
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
) = range(6, 20, 1)

# Address form states
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
) = range(20, 30, 1)

# File upload states
(
    FILE_UPLOAD_ID_DOC,
    FILE_UPLOAD_BIRTH_CERT,
    PAYMENT_METHOD_STATE,
    SEND_CONFIRMATION_STATE,
    SEND_PAYMENT_INSTRUCTION
) = range(30, 35)

MAIN_MENU = 100
HELP_MENU = 1000
AFTER_START = 2000

# Dropdown Sequence Configuration
DROPDOWN_SEQUENCE = [
    ('select[name="gender"]', "Gender", 2),
    ('select[name="martialStatus"]', "Marital Status", 3),
]

# Pagination configuration
OCCUPATION_PAGE_SIZE = 8
PAGINATION_PREFIX = "page_"

async def ask_region(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_region:Start] Entering ask_region function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    logger.info(f"[ask_region:GetPage] Retrieving page for chat_id {chat_id}")
    page = active_sessions[chat_id]['page']
    logger.info("[ask_region:ReplyText] Sending region selection prompt")
    await message.reply_text("Please select your region.")
    logger.info("[ask_region:LocateSelect] Locating region select element")
    select_locator = page.locator("select.form-control").nth(0)
    logger.info("[ask_region:WaitForSelect] Waiting for select element to be visible")
    await select_locator.wait_for()
    logger.info("[ask_region:GetOptions] Retrieving options from select element")
    options = await select_locator.locator('option').all()
    valid_options = []
    
    logger.info("[ask_region:ProcessOptions] Processing select options")
    for opt in options:
        value = await opt.get_attribute("value")
        text = (await opt.inner_text()).strip()
        if value and "--" not in text:
            valid_options.append((value, text))
    logger.info(f"[ask_region:ValidOptions] Found {len(valid_options)} valid options")

    logger.info("[ask_region:StoreOptions] Storing region options in user_data")
    context.user_data["region_options"] = valid_options

    logger.info("[ask_region:CreateKeyboard] Creating inline keyboard for regions")
    keyboard = []
    for i in range(0, len(valid_options), 3):
        row = []
        if i < len(valid_options):
            value, text = valid_options[i]
            row.append(InlineKeyboardButton(text, callback_data=f"region_{value}"))
        if i + 1 < len(valid_options):
            value, text = valid_options[i + 1]
            row.append(InlineKeyboardButton(text, callback_data=f"region_{value}"))
        if i + 2 < len(valid_options):
            value, text = valid_options[i + 2]
            row.append(InlineKeyboardButton(text, callback_data=f"region_{value}"))
        keyboard.append(row)

    logger.info("[ask_region:SendKeyboard] Sending region selection keyboard")
    reply_markup = InlineKeyboardMarkup(keyboard)
    await message.reply_text("Please select a Region:", reply_markup=reply_markup)
    logger.info("[ask_region:Return] Returning state 0")
    return 0

async def ask_region_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_region_response:Start] Entering ask_region_response function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    query = update.callback_query
    logger.info("[ask_region_response:AnswerQuery] Answering callback query")
    await query.answer()
    
    logger.info("[ask_region_response:GetSelectedValue] Extracting selected region value")
    selected_value = query.data.replace("region_", "")
    logger.info(f"[ask_region_response:SelectOption] Selecting option {selected_value} on page")
    region_select = active_sessions[chat_id]['page'].locator("select.form-control").nth(0)
    await region_select.select_option(value=selected_value)
    
    logger.info("[ask_region_response:TriggerChange] Triggering change event on region select")
    await active_sessions[chat_id]['page'].evaluate(
        """() => {
            const select = document.querySelectorAll("select.form-control")[0];
            select.dispatchEvent(new Event('change', { bubbles: true }));
        }"""
    )
    logger.info("[ask_region_response:GetRegionName] Retrieving region name")
    region_name = next((text for value, text in context.user_data["region_options"] if value == selected_value), "Unknown")

    logger.info(f"[ask_region_response:EditMessage] Updating message with selected region: {region_name}")
    await query.edit_message_text(text=f"✅ Region selected: {region_name}!")
    logger.info("[ask_region_response:StoreRegion] Storing selected region in user_data")
    context.user_data["selected_region"] = region_name
    logger.info("[ask_region_response:CallAskCity] Calling ask_city function")
    return await ask_city(update, context)

async def ask_city(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_city:Start] Entering ask_city function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    logger.info("[ask_city:LocateSelect] Locating city select element")
    select_locator = page.locator("select.form-control").nth(1)
    logger.info("[ask_city:WaitForSelect] Waiting for city select element to be visible")
    await select_locator.wait_for()
    
    MAX_RETRIES = 10
    city_options = []
    
    logger.info("[ask_city:FetchOptions] Attempting to fetch city options")
    for attempt in range(MAX_RETRIES):
        logger.info(f"[ask_city:FetchOptionsAttempt] Attempt {attempt + 1}/{MAX_RETRIES}")
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
            logger.info(f"[ask_city:OptionsFound] Found {len(city_options)} city options")
            break
    
    if not city_options:
        logger.error("[ask_city:NoOptions] Failed to load city options")
        await message.reply_text("❌ Failed to load city options. Please try again.")
        return ConversationHandler.END

    logger.info("[ask_city:StoreOptions] Storing city options in user_data")
    context.user_data["city_options"] = city_options
    
    logger.info("[ask_city:CreateKeyboard] Creating inline keyboard for cities")
    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"city_{value}")] for value, text in city_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.info("[ask_city:SendKeyboard] Sending city selection keyboard")
    await message.reply_text("Please select a City:", reply_markup=reply_markup)
    
    logger.info("[ask_city:Return] Returning state 1")
    return 1

async def ask_city_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_city_response:Start] Entering ask_city_response function")
    query = update.callback_query
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    logger.info("[ask_city_response:AnswerQuery] Answering callback query")
    await query.answer()
    
    logger.info("[ask_city_response:GetSelectedValue] Extracting selected city value")
    selected_value = query.data.replace("city_", "")
    logger.info(f"[ask_city_response:SelectOption] Selecting city option {selected_value} on page")
    await active_sessions[chat_id]['page'].locator("select.form-control").nth(1).select_option(value=selected_value)
    logger.info("[ask_city_response:GetCityName] Retrieving city name")
    city_name = next((text for value, text in context.user_data["city_options"] if value == selected_value), "Unknown")

    logger.info(f"[ask_city_response:EditMessage] Updating message with selected city: {city_name}")
    await query.edit_message_text(text=f"✅ City selected: {city_name}!")
    logger.info("[ask_city_response:StoreCity] Storing selected city in user_data")
    context.user_data["selected_city"] = city_name
    logger.info("[ask_city_response:CallAskOffice] Calling ask_office function")
    return await ask_office(update, context)

async def ask_office(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_office:Start] Entering ask_office function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    
    logger.info("[ask_office:LocateSelect] Locating office select element")
    select_locator = page.locator("select.form-control").nth(2)
    logger.info("[ask_office:WaitForSelect] Waiting for office select element to be visible")
    await select_locator.wait_for()
    
    MAX_RETRIES = 10
    office_options = []
    
    logger.info("[ask_office:FetchOptions] Attempting to fetch office options")
    for attempt in range(MAX_RETRIES):
        logger.info(f"[ask_office:FetchOptionsAttempt] Attempt {attempt + 1}/{MAX_RETRIES}")
        await page.wait_for_timeout(500)
        office_options = await page.evaluate("""
            () => {
                const select = document.querySelectorAll("select.form-control")[2];
                return Array.from(select.options)
                    .filter(opt => {
                        const txt = opt.textContent.trim().toLowerCase();
                        return opt.value && txt !== "" && !txt.includes("select") && !txt.includes("--");
                    })
                    .map(opt => [opt.value, opt.textContent.trim()]);
            }
        """)
        if office_options:
            logger.info(f"[ask_office:OptionsFound] Found {len(office_options)} office options")
            break

    if not office_options:
        logger.error("[ask_office:NoOptions] Failed to load office options")
        await message.reply_text("❌ Failed to load office options. Please try again.")
        return ConversationHandler.END

    logger.info("[ask_office:StoreOptions] Storing office options in user_data")
    context.user_data["office_options"] = office_options

    logger.info("[ask_office:CreateKeyboard] Creating inline keyboard for offices")
    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"office_{value}")] for value, text in office_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.info("[ask_office:SendKeyboard] Sending office selection keyboard")
    await message.reply_text("Please select an Office:", reply_markup=reply_markup)

    logger.info("[ask_office:Return] Returning state 2")
    return 2

async def ask_office_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_office_response:Start] Entering ask_office_response function")
    query = update.callback_query
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    logger.info("[ask_office_response:AnswerQuery] Answering callback query")
    await query.answer()
    
    logger.info("[ask_office_response:GetSelectedValue] Extracting selected office value")
    selected_value = query.data.replace("office_", "")
    logger.info(f"[ask_office_response:SelectOption] Selecting office option {selected_value} on page")
    await active_sessions[chat_id]['page'].locator("select.form-control").nth(2).select_option(value=selected_value)
    logger.info("[ask_office_response:GetOfficeName] Retrieving office name")
    office_name = next((text for value, text in context.user_data["office_options"] if value == selected_value), "Unknown")
    logger.info(f"[ask_office_response:EditMessage] Updating message with selected office: {office_name}")
    await query.edit_message_text(text=f"✅ Office selected: {office_name}!")
    logger.info("[ask_office_response:CallAskBranch] Calling ask_branch function")
    return await ask_branch(update, context)

async def ask_branch(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_branch:Start] Entering ask_branch function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    logger.info("[ask_branch:LocateSelect] Locating branch select element")
    select_locator = page.locator("select.form-control").nth(3)
    logger.info("[ask_branch:WaitForSelect] Waiting for branch select element to be visible")
    await select_locator.wait_for()

    MAX_RETRIES = 10
    branch_options = []

    logger.info("[ask_branch:FetchOptions] Attempting to fetch branch options")
    for attempt in range(MAX_RETRIES):
        logger.info(f"[ask_branch:FetchOptionsAttempt] Attempt {attempt + 1}/{MAX_RETRIES}")
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
            logger.info(f"[ask_branch:OptionsFound] Found {len(branch_options)} branch options")
            break

    if not branch_options:
        logger.error("[ask_branch:NoOptions] Failed to load branch options")
        await message.reply_text("❌ Failed to load branch options. Please try again.")
        return ConversationHandler.END

    logger.info("[ask_branch:StoreOptions] Storing branch options in user_data")
    context.user_data["branch_options"] = branch_options

    logger.info("[ask_branch:CreateKeyboard] Creating inline keyboard for branches")
    keyboard = [
        [InlineKeyboardButton(text, callback_data=f"branch_{value}")] for value, text in branch_options
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.info("[ask_branch:SendKeyboard] Sending branch selection keyboard")
    await message.reply_text("Please select a Branch:", reply_markup=reply_markup)

    logger.info("[ask_branch:Return] Returning state 3")
    return 3

async def ask_branch_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_branch_response:Start] Entering ask_branch_response function")
    message = update.message or update.callback_query.message
    query = update.callback_query
    chat_id = message.chat.id
    logger.info("[ask_branch_response:AnswerQuery] Answering callback query")
    await query.answer()
    
    logger.info("[ask_branch_response:GetSelectedValue] Extracting selected branch value")
    selected_value = query.data.replace("branch_", "")
    page = active_sessions[chat_id]['page']
    logger.info(f"[ask_branch_response:SelectOption] Selecting branch option {selected_value} on page")
    await page.locator("select.form-control").nth(3).select_option(value=selected_value)
    logger.info("[ask_branch_response:GetBranchName] Retrieving branch name")
    branch_name = next((text for value, text in context.user_data["branch_options"] if value == selected_value), "Unknown")
    logger.info(f"[ask_branch_response:EditMessage] Updating message with selected branch: {branch_name}")
    await query.edit_message_text(text=f"✅ Branch selected: {branch_name}!")
    
    logger.info("[ask_branch_response:ClickNext] Clicking Next button")
    await page.get_by_role("button", name="Next").click()
    logger.info("[ask_branch_response:Wait] Waiting for page to process")
    await page.wait_for_timeout(3000)
    logger.info("[ask_branch_response:SendStatus] Sending status message")
    status_msg = await message.reply_text("Checking available dates... from current month...")
    logger.info("[ask_branch_response:UpdateStatus] Updating status message")
    await status_msg.edit_text("almost there...checking available dates...")
    logger.info("[ask_branch_response:CallAskDate] Calling ask_date function")
    return await ask_date(update, context, status_msg)

async def ask_date(update: Update, context: ContextTypes.DEFAULT_TYPE, status_msg) -> int:
    logger.info("[ask_date:Start] Entering ask_date function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    logger.info("[ask_date:UpdateStatus] Updating status message to check dates")
    await status_msg.edit_text("Checking available dates...please wait")
    logger.info("[ask_date:CheckCalendar] Checking if calendar is visible")
    calendar_visible = await page.locator("div.react-calendar__month-view__days").is_visible()
    if not calendar_visible:
        logger.error("[ask_date:NoCalendar] Calendar not visible")
        await message.reply_text("Sorry, we couldn't find any available dates. Please try again later.")
        logger.info("[ask_date:CallNewOrCheck] Calling new_or_check function")
        return await new_or_check(update, context)
    
    logger.info("[ask_date:CalendarVisible] Calendar is visible")
    await status_msg.edit_text("Calendar is visible, checking for available dates...")
    
    logger.info("[ask_date:FetchDays] Fetching available day buttons")
    while True:
        day_buttons = await page.locator("div.react-calendar__month-view__days button:not([disabled])").all()
        logger.info(f"[ask_date:DaysFound] Found {len(day_buttons)} available dates")
        await status_msg.edit_text(f"Found {len(day_buttons)} available dates.")
        if day_buttons:
            break
        logger.info("[ask_date:ClickNextMonth] Clicking next month button")
        await page.locator("button.react-calendar__navigation__next-button").click()
        logger.info("[ask_date:WaitNextMonth] Waiting after clicking next month")
        await page.wait_for_timeout(1000)
    
    logger.info("[ask_date:ExtractDates] Extracting available dates")
    await status_msg.edit_text("Extracting available dates...")
    available_days = []
    for i, button in enumerate(day_buttons, start=1):
        label = await button.locator("abbr").get_attribute("aria-label")
        if label:
            available_days.append((i, label, button))
    logger.info(f"[ask_date:DatesExtracted] Extracted {len(available_days)} available days")

    logger.info("[ask_date:StoreDays] Storing available days in user_data")
    context.user_data["available_days"] = available_days

    logger.info("[ask_date:CreateKeyboard] Creating inline keyboard for dates")
    keyboard = [
        [InlineKeyboardButton(label, callback_data=f"date_{i}")] for i, label, _ in available_days
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.info("[ask_date:SendKeyboard] Sending date selection keyboard")
    await status_msg.edit_text("📅 Available Dates:", reply_markup=reply_markup)

    logger.info("[ask_date:Return] Returning state 4")
    return 4

async def ask_date_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_date_response:Start] Entering ask_date_response function")
    query = update.callback_query
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    logger.info("[ask_date_response:AnswerQuery] Answering callback query")
    await query.answer()
    
    logger.info("[ask_date_response:GetSelectedIndex] Extracting selected date index")
    selected_idx = int(query.data.replace("date_", ""))
    logger.info(f"[ask_date_response:SelectedIndex] Selected index: {selected_idx}")
    available_days = context.user_data["available_days"]
    
    logger.info("[ask_date_response:ClickDate] Clicking selected date")
    for i, label, button in available_days:
        if i == selected_idx:
            await button.click()
            logger.info(f"[ask_date_response:EditMessage] Updating message with selected date: {label}")
            await query.edit_message_text(text=f"✅ Selected date: {label}")
            break

    logger.info("[ask_date_response:Wait] Waiting for page to process")
    await active_sessions[chat_id]['page'].wait_for_timeout(1000)
    logger.info("[ask_date_response:CallHandleTimeSlot] Calling handle_time_slot function")
    return await handle_time_slot(update, context)

async def handle_time_slot(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_time_slot:Start] Entering handle_time_slot function")
    page = active_sessions[update.effective_chat.id]['page']
    message = update.message or update.callback_query.message
    logger.info("[handle_time_slot:SendStatus] Sending status message for time slots")
    status_msg = await message.reply_text("Checking for available time slots...")
    
    logger.info("[handle_time_slot:FetchMorning] Fetching morning time slots")
    morning_buttons = await page.locator("table#displayMorningAppts input.btn_select").all()
    logger.info("[handle_time_slot:FetchAfternoon] Fetching afternoon time slots")
    afternoon_buttons = await page.locator("table#displayAfternoonAppts input.btn_select").all()
  
    if not morning_buttons and not afternoon_buttons:
        logger.error("[handle_time_slot:NoSlots] No time slots available")
        await status_msg.edit_text("❌ No time slots available.")
        logger.info("[handle_time_slot:CallAskDate] Calling ask_date function")
        return await ask_date(update, context, status_msg)
    
    if morning_buttons:
        logger.info("[handle_time_slot:MorningSlots] Morning slots available")
        await status_msg.edit_text("🕒 Morning slots available.")
        logger.info("[handle_time_slot:SelectMorning] Selecting first morning slot")
        await morning_buttons[0].click()
        logger.info("[handle_time_slot:UpdateMorningStatus] Updating status for morning slot")
        await status_msg.edit_text("🕒 Morning time slot selected.")
    elif afternoon_buttons:
        logger.info("[handle_time_slot:AfternoonSlots] Afternoon slots available")
        await status_msg.edit_text("🕒 Afternoon slots available.")
        logger.info("[handle_time_slot:SelectAfternoon] Selecting first afternoon slot")
        await afternoon_buttons[0].click()
        logger.info("[handle_time_slot:UpdateAfternoonStatus] Updating status for afternoon slot")
        await status_msg.edit_text("🕒 Afternoon time slot selected.")
    
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    logger.info("[handle_time_slot:ClickNext] Clicking Next button")
    await page.get_by_role("button", name="Next").click()
    logger.info("[handle_time_slot:Wait] Waiting for page to process")
    await page.wait_for_timeout(1000)
    logger.info("[handle_time_slot:CallAskFirstName] Calling ask_first_name function")
    return await ask_first_name(update, context)

async def ask_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_first_name:Start] Entering ask_first_name function")
    message = update.message or update.callback_query.message
    logger.info("[ask_first_name:ReplyText] Sending prompt for first name")
    await message.reply_text("Enter your First Name:")
    logger.info("[ask_first_name:Return] Returning PERSONAL_FIRSTNAME state")
    return PERSONAL_FIRSTNAME

async def handle_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_first_name:Start] Entering handle_first_name function")
    message = update.message or update.callback_query.message
    logger.info("[handle_first_name:StoreFirstName] Storing first name in user_data")
    context.user_data["first_name"] = message.text.strip()
    logger.info("[handle_first_name:ReplyText] Sending prompt for middle name")
    await message.reply_text("Enter your Middle Name:")
    logger.info("[handle_first_name:Return] Returning PERSONAL_MIDDLENAME state")
    return PERSONAL_MIDDLENAME

async def handle_middle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_middle_name:Start] Entering handle_middle_name function")
    message = update.message or update.callback_query.message
    logger.info("[handle_middle_name:StoreMiddleName] Storing middle name in user_data")
    context.user_data["middle_name"] = message.text.strip()
    logger.info("[handle_middle_name:ReplyText] Sending prompt for last name")
    await message.reply_text("Enter your Last Name:")
    logger.info("[handle_middle_name:Return] Returning PERSONAL_LASTNAME state")
    return PERSONAL_LASTNAME

async def handle_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_last_name:Start] Entering handle_last_name function")
    message = update.message or update.callback_query.message
    logger.info("[handle_last_name:StoreLastName] Storing last name in user_data")
    context.user_data["last_name"] = message.text.strip()
    logger.info("[handle_last_name:ReplyText] Sending prompt for Amharic first name")
    await message.reply_text("Enter your First Name in Amharic:")
    logger.info("[handle_last_name:Return] Returning PERSONAL_GEZZ_FIRSTNAME state")
    return PERSONAL_GEZZ_FIRSTNAME

async def handle_gez_first_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_gez_first_name:Start] Entering handle_gez_first_name function")
    message = update.message or update.callback_query.message
    logger.info("[handle_gez_first_name:StoreGezFirstName] Storing Amharic first name in user_data")
    context.user_data["amharic_first_name"] = message.text.strip()
    logger.info("[handle_gez_first_name:ReplyText] Sending prompt for Amharic middle name")
    await message.reply_text("Enter your Middle Name in Amharic:")
    logger.info("[handle_gez_first_name:Return] Returning PERSONAL_GEZZ_MIDDLENAME state")
    return PERSONAL_GEZZ_MIDDLENAME

async def handle_gez_middle_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_gez_middle_name:Start] Entering handle_gez_middle_name function")
    message = update.message or update.callback_query.message
    logger.info("[handle_gez_middle_name:StoreGezMiddleName] Storing Amharic middle name in user_data")
    context.user_data["amharic_middle_name"] = message.text.strip()
    logger.info("[handle_gez_middle_name:ReplyText] Sending prompt for Amharic last name")
    await message.reply_text("Enter your Last Name in Amharic:")
    logger.info("[handle_gez_middle_name:Return] Returning PERSONAL_GEZZ_LASTNAME state")
    return PERSONAL_GEZZ_LASTNAME

async def handle_gez_last_name(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_gez_last_name:Start] Entering handle_gez_last_name function")
    message = update.message or update.callback_query.message
    logger.info("[handle_gez_last_name:StoreGezLastName] Storing Amharic last name in user_data")
    context.user_data["amharic_last_name"] = message.text.strip()
    logger.info("[handle_gez_last_name:ReplyText] Sending prompt for birth place")
    await message.reply_text("Enter your Birth Place:")
    logger.info("[handle_gez_last_name:Return] Returning PERSONAL_BIRTHPLACE state")
    return PERSONAL_BIRTHPLACE

async def handle_birth_place(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_birth_place:Start] Entering handle_birth_place function")
    message = update.message or update.callback_query.message
    logger.info("[handle_birth_place:StoreBirthPlace] Storing birth place in user_data")
    context.user_data["birth_place"] = message.text.strip()
    logger.info("[handle_birth_place:ReplyText] Sending prompt for phone number")
    await message.reply_text(
        " Enter your Phone Number:\n"
        "• Format: 0912345678 or 0712345678\n"
        "• Ethiopian phone numbers should start with 09 or 07.\n"
        "• Please enter a valid 10-digit number."
    )
    logger.info("[handle_birth_place:Return] Returning PERSONAL_PHONE_NUMBER state")
    return PERSONAL_PHONE_NUMBER

async def handle_phone_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_phone_number:Start] Entering handle_phone_number function")
    message = update.message or update.callback_query.message
    phone_number = message.text.strip()
    logger.info("[handle_phone_number:CleanNumber] Cleaning phone number")
    cleaned_number = ''.join(filter(str.isdigit, phone_number))
    
    logger.info("[handle_phone_number:ValidateNumber] Validating phone number")
    if (len(cleaned_number) == 10 and 
        cleaned_number.startswith(('09', '07')) and
        cleaned_number[2:].isdigit()):
        
        logger.info("[handle_phone_number:StoreNumber] Storing valid phone number in user_data")
        context.user_data["phone_number"] = cleaned_number
        logger.info("[handle_phone_number:ReplyText] Sending prompt for date of birth")
        await message.reply_text(
            "Enter your Date of Birth:\n"
            "• Format: mm/dd/yyyy(Gregorian)\n"
            "• Or use Ethiopian date: yyyy/mm/dd (e.g., 2015/03/12)"
        )   
        logger.info("[handle_phone_number:Return] Returning PERSONAL_DOB state")
        return PERSONAL_DOB
    
    logger.error("[handle_phone_number:InvalidNumber] Invalid phone number provided")
    await message.reply_text(
        "❌ Invalid Ethiopian phone number. Please enter a 10-digit number starting with 09 or 07.\n"
        "Example: 0912345678 or 0712345678"
    )
    logger.info("[handle_phone_number:ReturnInvalid] Returning PERSONAL_PHONE_NUMBER state for retry")
    return PERSONAL_PHONE_NUMBER

def validate_gregorian_date(date_str):
    logger.info("[validate_gregorian_date:Start] Entering validate_gregorian_date function")
    try:
        if '/' in date_str:
            logger.info("[validate_gregorian_date:TryFormat1] Trying mm/dd/yyyy format")
            date_obj = datetime.strptime(date_str, "%m/%d/%Y")
        else:
            logger.info("[validate_gregorian_date:CheckLength] Checking length for mmddyyyy format")
            if len(date_str) != 8:
                logger.error("[validate_gregorian_date:InvalidLength] Invalid date length")
                return False
            logger.info("[validate_gregorian_date:TryFormat2] Trying mmddyyyy format")
            date_obj = datetime.strptime(date_str, "%m%d%Y")
        
        logger.info("[validate_gregorian_date:SanityCheck] Performing year sanity check")
        if date_obj.year < 1900 or date_obj.year > datetime.now().year:
            logger.error("[validate_gregorian_date:InvalidYear] Year out of valid range")
            return False
        logger.info("[validate_gregorian_date:Success] Date validated successfully")
        return date_obj
    except ValueError:
        logger.error("[validate_gregorian_date:InvalidFormat] Invalid date format")
        return False

def convert_ethiopian_to_gregorian(eth_date_str):
    logger.info("[convert_ethiopian_to_gregorian:Start] Entering convert_ethiopian_to_gregorian function")
    try:
        logger.info("[convert_ethiopian_to_gregorian:ValidateFormat] Validating Ethiopian date format")
        if not re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', eth_date_str):
            logger.error("[convert_ethiopian_to_gregorian:InvalidFormat] Invalid Ethiopian date format")
            return False
            
        logger.info("[convert_ethiopian_to_gregorian:ParseDate] Parsing Ethiopian date")
        year, month, day = map(int, eth_date_str.split('/'))
        
        logger.info("[convert_ethiopian_to_gregorian:ValidateValues] Validating Ethiopian date values")
        if month < 1 or month > 13 or day < 1 or day > 30:
            logger.error("[convert_ethiopian_to_gregorian:InvalidValues] Invalid Ethiopian date values")
            return False
        if month == 13 and day > 5:
            logger.error("[convert_ethiopian_to_gregorian:InvalidPagume] Invalid Ethiopian date for Pagume")
            return False
            
        logger.info("[convert_ethiopian_to_gregorian:Convert] Converting to Gregorian date")
        greg_date = EthiopianDateConverter.to_gregorian(year, month, day)
        
        logger.info("[convert_ethiopian_to_gregorian:SanityCheck] Performing final sanity check")
        if greg_date.year < 1900 or greg_date > datetime.now().date():
            logger.error("[convert_ethiopian_to_gregorian:InvalidRange] Converted date out of valid range")
            return False
            
        logger.info("[convert_ethiopian_to_gregorian:Success] Successfully converted date")
        return greg_date

    except Exception as e:
        logger.error(f"[convert_ethiopian_to_gregorian:Error] Error converting Ethiopian date: {e}")
        return False

async def handle_dob(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_dob:Start] Entering handle_dob function")
    message = update.message or update.callback_query.message
    dob_input = message.text.strip()
    
    logger.info("[handle_dob:CheckEthiopic] Checking for Ethiopic characters")
    if re.search(r'[ሀ-ፕ]|[\u1369-\u137C]', dob_input):
        logger.error("[handle_dob:EthiopicDetected] Ethiopic characters detected")
        await message.reply_text("Please enter the date in English numbers (0-9)")
        logger.info("[handle_dob:ReturnEthiopic] Returning PERSONAL_DOB state for retry")
        return PERSONAL_DOB
    
    logger.info("[handle_dob:CheckEthiopianFormat] Checking for Ethiopian date format")
    if '/' in dob_input and (dob_input.count('/') == 2 and re.match(r'^\d{4}/\d{1,2}/\d{1,2}$', dob_input)):
        logger.info("[handle_dob:EthiopianDetected] Ethiopian date format detected")
        greg_date = convert_ethiopian_to_gregorian(dob_input)
        if greg_date:
            logger.info("[handle_dob:StoreEthiopian] Storing converted Gregorian date")
            context.user_data["dob"] = greg_date.strftime("%m/%d/%Y")
            logger.info(f"[handle_dob:ReplyConverted] Replying with converted date: {context.user_data['dob']}")
            await message.reply_text(f"Converted to Gregorian: {context.user_data['dob']}")
            logger.info("[handle_dob:CallAskDropdown] Calling ask_dropdown_option function")
            return await ask_dropdown_option(update, context)
    
    logger.info("[handle_dob:ValidateGregorian] Validating Gregorian date")
    date_obj = validate_gregorian_date(dob_input)
    logger.info(f"[handle_dob:GregorianResult] Gregorian validation result: {date_obj}")
    if date_obj:
        logger.info("[handle_dob:StoreGregorian] Storing Gregorian date in user_data")
        context.user_data["dob"] = date_obj.strftime("%m/%d/%Y")
        logger.info("[handle_dob:CallAskDropdown] Calling ask_dropdown_option function")
        return await ask_dropdown_option(update, context)
    
    logger.error("[handle_dob:InvalidDate] Invalid date format provided")
    await message.reply_text(
        "❌ Invalid date format. Please enter:\n"
        "• Ethiopian: YYYY/MM/DD (e.g., 2012/09/12)\n"
        "• Gregorian: mm/dd/yyyy (e.g., 05/21/1990)\n"
        "• Month (1-12), Day (1-31), Year (1900-now)"
    )
    logger.info("[handle_dob:ReturnInvalid] Returning PERSONAL_DOB state for retry")
    return PERSONAL_DOB

async def ask_dropdown_option(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_dropdown_option:Start] Entering ask_dropdown_option function")
    message = update.message or update.callback_query.message
    logger.info("[ask_dropdown_option:GetStep] Retrieving current dropdown step")
    step = context.user_data.get("dropdown_step", 0)
    
    if step >= len(DROPDOWN_SEQUENCE):
        logger.info("[ask_dropdown_option:EndSequence] Dropdown sequence completed")
        logger.info("[ask_dropdown_option:CallFillPersonal] Calling fill_personal_form_on_page")
        return await fill_personal_form_on_page(update, context)

    selector, label, buttons_per_row = DROPDOWN_SEQUENCE[step]
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    logger.info(f"[ask_dropdown_option:LocateDropdown] Locating dropdown: {selector}")
    dropdown = page.locator(selector)
    logger.info("[ask_dropdown_option:WaitForDropdown] Waiting for dropdown to be visible")
    await dropdown.wait_for()
    logger.info("[ask_dropdown_option:GetOptions] Retrieving dropdown options")
    options = await dropdown.locator('option').all()

    valid_options = []
    logger.info("[ask_dropdown_option:ProcessOptions] Processing dropdown options")
    for opt in options:
        value = await opt.get_attribute("value")
        text = (await opt.inner_text()).strip()
        if value and "--" not in text:
            valid_options.append((value, text))
    logger.info(f"[ask_dropdown_option:ValidOptions] Found {len(valid_options)} valid options")

    logger.info("[ask_dropdown_option:StoreOptions] Storing dropdown options in user_data")
    context.user_data["dropdown_options"] = valid_options
    logger.info("[ask_dropdown_option:StoreSelector] Storing current dropdown selector")
    context.user_data["current_dropdown_selector"] = selector

    logger.info("[ask_dropdown_option:CreateKeyboard] Creating inline keyboard for dropdown")
    keyboard = []
    row = []
    for i, (value, text) in enumerate(valid_options, 1):
        row.append(InlineKeyboardButton(text, callback_data=f"dropdown_{step}_{value}"))
        if i % buttons_per_row == 0 or i == len(valid_options):
            keyboard.append(row)
            row = []

    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.info(f"[ask_dropdown_option:SendKeyboard] Sending dropdown selection prompt for {label}")
    await message.reply_text(f"Please select {label}:", reply_markup=reply_markup)

    logger.info("[ask_dropdown_option:Return] Returning DROPDOWN_STATE")
    return DROPDOWN_STATE

async def handle_dropdown_response(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_dropdown_response:Start] Entering handle_dropdown_response function")
    query = update.callback_query
    message = update.message or update.callback_query.message
    logger.info("[handle_dropdown_response:AnswerQuery] Answering callback query")
    await query.answer()
    
    logger.info("[handle_dropdown_response:ParseData] Parsing callback data")
    _, step, value = query.data.split("_")
    step = int(step)
    logger.info(f"[handle_dropdown_response:Step] Current step: {step}, value: {value}")
    options = context.user_data.get("dropdown_options", [])
    selector = context.user_data.get("current_dropdown_selector")

    logger.info("[handle_dropdown_response:FindOption] Finding selected option")
    selected_option = next((opt for opt in options if opt[0] == value), None)
    if not selected_option:
        logger.error("[handle_dropdown_response:InvalidSelection] Invalid dropdown selection")
        await query.edit_message_text(text="❌ Invalid selection. Please try again.")
        logger.info("[handle_dropdown_response:ReturnInvalid] Returning DROPDOWN_STATE for retry")
        return DROPDOWN_STATE

    value, label = selected_option
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    logger.info(f"[handle_dropdown_response:SelectOption] Selecting dropdown option: {value}")
    await page.select_option(selector, value)
    logger.info(f"[handle_dropdown_response:EditMessage] Updating message with selected option: {label}")
    await query.edit_message_text(text=f"✅ {label} selected.")

    logger.info("[handle_dropdown_response:NextStep] Incrementing dropdown step")
    context.user_data["dropdown_step"] = step + 1
    logger.info("[handle_dropdown_response:CallAskDropdown] Calling ask_dropdown_option function")
    return await ask_dropdown_option(update, context)

async def fill_personal_form_on_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[fill_personal_form_on_page:Start] Entering fill_personal_form_on_page function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    user_data = context.user_data
    
    logger.info("[fill_personal_form_on_page:FillFirstName] Filling first name")
    await page.fill('input[name="firstName"]', user_data["first_name"])
    logger.info("[fill_personal_form_on_page:FillMiddleName] Filling middle name")
    await page.fill('input[name="middleName"]', user_data["middle_name"])
    logger.info("[fill_personal_form_on_page:FillLastName] Filling last name")
    await page.fill('input[name="lastName"]', user_data["last_name"])
    logger.info("[fill_personal_form_on_page:ClearDOB] Clearing date of birth field")
    await page.fill('#date-picker-dialog', '')
    logger.info("[fill_personal_form_on_page:TypeDOB] Typing date of birth")
    await page.type('#date-picker-dialog', user_data["dob"])
    logger.info("[fill_personal_form_on_page:FillGezFirstName] Filling Amharic first name")
    await page.fill('input[name="geezFirstName"]', user_data["amharic_first_name"])
    logger.info("[fill_personal_form_on_page:FillGezMiddleName] Filling Amharic middle name")
    await page.fill('input[name="geezMiddleName"]', user_data["amharic_middle_name"])
    logger.info("[fill_personal_form_on_page:FillGezLastName] Filling Amharic last name")
    await page.fill('input[name="geezLastName"]', user_data["amharic_last_name"])
    logger.info("[fill_personal_form_on_page:SelectNationality] Selecting nationality")
    await page.select_option('select[name="nationalityId"]', "ETHIOPIA")   
    logger.info("[fill_personal_form_on_page:FillPhone] Filling phone number")
    await page.fill('input[name="phoneNumber"]', user_data["phone_number"])
    logger.info("[fill_personal_form_on_page:FillBirthPlace] Filling birth place")
    await page.fill('input[name="birthPlace"]', user_data["birth_place"])

    logger.info("[fill_personal_form_on_page:ClickNext] Clicking Next button")
    await page.get_by_role("button", name="Next").click()
    logger.info("[fill_personal_form_on_page:WaitForRegion] Waiting for region select")
    await page.wait_for_selector('select[name="region"]', timeout=50000)
    logger.info("[fill_personal_form_on_page:SelectRegion] Selecting region")
    region_select = page.locator("select[name='region']")
    selected_region = context.user_data["selected_region"]
    await region_select.select_option(value=selected_region)

    logger.info("[fill_personal_form_on_page:CallFillAddress] Calling fill_address_form_on_page")
    return await fill_address_form_on_page(update, context)

async def fill_address_form_on_page(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[fill_address_form_on_page:Start] Entering fill_address_form_on_page function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    user_data = context.user_data
    
    logger.info("[fill_address_form_on_page:FillCity] Filling city")
    await page.fill('input[name="city"]', user_data["selected_city"])
    logger.info("[fill_address_form_on_page:ClickNext1] Clicking first Next button")
    await page.get_by_role("button", name="Next").click()
    logger.info("[fill_address_form_on_page:ClickNext2] Clicking second Next button")
    await page.get_by_role("button", name="Next").click()
    logger.info("[fill_address_form_on_page:ClickSubmit] Clicking Submit button")
    await page.get_by_role("button", name="Submit").click()

    logger.info("[fill_address_form_on_page:CallFileUpload] Calling file_upload_from_telegram")
    return await file_upload_from_telegram(update, context)

async def file_upload_from_telegram(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[file_upload_from_telegram:Start] Entering file_upload_from_telegram function")
    message = update.message or update.callback_query.message
    logger.info("[file_upload_from_telegram:CreateKeyboard] Creating file upload keyboard")
    keyboard = [
        [InlineKeyboardButton("📤 Upload ID Document", callback_data="upload_id")],
        [InlineKeyboardButton("📤 Upload Birth Certificate", callback_data="upload_birth")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.info("[file_upload_from_telegram:SendPrompt] Sending file upload prompt")
    await message.reply_text(
        "📤 Please upload your documents:",
        reply_markup=reply_markup
    )
    logger.info("[file_upload_from_telegram:Return] Returning FILE_UPLOAD_ID_DOC state")
    return FILE_UPLOAD_ID_DOC

async def handle_file_upload(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_file_upload:Start] Entering handle_file_upload function")
    message = update.message or update.callback_query.message
    ALLOWED_EXTENSIONS = {'jpeg', 'jpg', 'png', 'gif', 'pdf'}
    MAX_FILE_SIZE_MB = 1
    
    if update.callback_query:
        query = update.callback_query
        logger.info("[handle_file_upload:AnswerQuery] Answering callback query")
        await query.answer()
        
        if query.data == "upload_id":
            logger.info("[handle_file_upload:SetIDType] Setting file type to id_doc")
            context.user_data["current_file_type"] = "id_doc"
            logger.info("[handle_file_upload:PromptID] Sending ID upload prompt")
            await query.edit_message_text(text="Please upload your **Valid Resident/Gov Employee ID** (JPEG, PNG, PDF, <1MB).")
            logger.info("[handle_file_upload:ReturnID] Returning FILE_UPLOAD_ID_DOC state")
            return FILE_UPLOAD_ID_DOC
        elif query.data == "upload_birth":
            logger.info("[handle_file_upload:SetBirthType] Setting file type to birth_cert")
            context.user_data["current_file_type"] = "birth_cert"
            logger.info("[handle_file_upload:PromptBirth] Sending birth certificate upload prompt")
            await query.edit_message_text(text="Please upload your **Authenticated Birth Certificate** (JPEG, PNG, PDF, <1MB).")
            logger.info("[handle_file_upload:ReturnBirth] Returning FILE_UPLOAD_BIRTH_CERT state")
            return FILE_UPLOAD_BIRTH_CERT
    
    logger.info("[handle_file_upload:GetFile] Retrieving uploaded file")
    file = message.document or (message.photo[-1] if message.photo else None)

    if not file:
        logger.error("[handle_file_upload:NoFile] No file provided")
        await message.reply_text("❌ Please send a file (image or document).")
        logger.info(f"[handle_file_upload:ReturnNoFile] Returning state for {context.user_data['current_file_type']}")
        return FILE_UPLOAD_ID_DOC if context.user_data["current_file_type"] == "id_doc" else FILE_UPLOAD_BIRTH_CERT

    logger.info("[handle_file_upload:CheckExtension] Checking file extension")
    if hasattr(file, "file_name"):
        ext = file.file_name.split('.')[-1].lower()
    else:
        ext = "jpg"
    logger.info(f"[handle_file_upload:FileExtension] File extension: {ext}")

    if ext not in ALLOWED_EXTENSIONS:
        logger.error("[handle_file_upload:InvalidExtension] Unsupported file type")
        await message.reply_text("❌ Unsupported file type. Use JPEG, PNG, PDF, etc.")
        logger.info(f"[handle_file_upload:ReturnInvalidExt] Returning state for {context.user_data['current_file_type']}")
        return FILE_UPLOAD_ID_DOC if context.user_data["current_file_type"] == "id_doc" else FILE_UPLOAD_BIRTH_CERT

    logger.info("[handle_file_upload:CheckSize] Checking file size")
    if file.file_size > MAX_FILE_SIZE_MB * 1024 * 1024:
        logger.error("[handle_file_upload:FileTooLarge] File size exceeds 1MB")
        await message.reply_text("❌ File too large. Must be less than 1MB.")
        logger.info(f"[handle_file_upload:ReturnTooLarge] Returning state for {context.user_data['current_file_type']}")
        return FILE_UPLOAD_ID_DOC if context.user_data["current_file_type"] == "id_doc" else FILE_UPLOAD_BIRTH_CERT

    logger.info("[handle_file_upload:PreparePath] Preparing file path")
    file_path = f"downloads/{context.user_data['current_file_type']}.{ext}"
    logger.info("[handle_file_upload:CreateDir] Creating downloads directory")
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    logger.info("[handle_file_upload:DownloadFile] Downloading file")
    tg_file = await file.get_file()
    await tg_file.download_to_drive(file_path)
    logger.info(f"[handle_file_upload:FileDownloaded] File downloaded to {file_path}")

    logger.info("[handle_file_upload:StoreFilePath] Storing file path in user_data")
    context.user_data[context.user_data["current_file_type"]] = file_path

    if context.user_data["current_file_type"] == "id_doc":
        logger.info("[handle_file_upload:IDUploaded] ID document uploaded")
        keyboard = [[InlineKeyboardButton("📤 Upload Birth Certificate", callback_data="upload_birth")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        logger.info("[handle_file_upload:PromptBirthCert] Sending birth certificate prompt")
        await message.reply_text("✅ ID uploaded. Please upload your birth certificate:", reply_markup=reply_markup)
        logger.info("[handle_file_upload:ReturnBirthCert] Returning FILE_UPLOAD_BIRTH_CERT state")
        return FILE_UPLOAD_BIRTH_CERT

    logger.info("[handle_file_upload:AllFilesUploaded] All files received")
    await message.reply_text("✅ All files received. Uploading to the form...")
    logger.info("[handle_file_upload:CallUploadFiles] Calling upload_files_to_form function")
    return await upload_files_to_form(update, context)

async def upload_files_to_form(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[upload_files_to_form:Start] Entering upload_files_to_form function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    
    try:
        logger.info("[upload_files_to_form:UploadID] Uploading ID document")
        await page.set_input_files('input[name="input-0"]', context.user_data["id_doc"])
        logger.info("[upload_files_to_form:UploadBirthCert] Uploading birth certificate")
        await page.set_input_files('input[name="input-1"]', context.user_data["birth_cert"])
        logger.info("[upload_files_to_form:ClickUpload] Clicking Upload button")
        await page.get_by_role("button", name="Upload").click()
        logger.info("[upload_files_to_form:ReplySuccess] Sending success message")
        await message.reply_text("📁 Uploaded successfully.")

        logger.info("[upload_files_to_form:ClickCheckbox] Clicking defaultUnchecked checkbox")
        await page.click('label[for="defaultUnchecked"]')
        logger.info("[upload_files_to_form:ClickNext] Clicking Next button")
        await page.get_by_role("button", name="Next").click()

        logger.info("[upload_files_to_form:CallAskPayment] Calling ask_payment_method function")
        return await ask_payment_method(update, context)
    finally:
        logger.info("[upload_files_to_form:Cleanup] Cleaning up uploaded files")
        for file_type in ["id_doc", "birth_cert"]:
            if file_path := context.user_data.get(file_type):
                try:
                    logger.info(f"[upload_files_to_form:DeleteFile] Deleting file {file_path}")
                    os.remove(file_path)
                except Exception as e:
                    logger.error(f"[upload_files_to_form:DeleteError] Error deleting file {file_path}: {e}")

async def ask_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_payment_method:Start] Entering ask_payment_method function")
    message = update.message or update.callback_query.message
    methods = ["CBE Birr", "TELE Birr", "CBE Mobile"]
    logger.info("[ask_payment_method:StoreMethods] Storing payment methods in user_data")
    context.user_data["payment_methods"] = methods

    logger.info("[ask_payment_method:CreateKeyboard] Creating payment method keyboard")
    keyboard = [
        [InlineKeyboardButton(method, callback_data=f"payment_{i}")] 
        for i, method in enumerate(methods)
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.info("[ask_payment_method:SendPrompt] Sending payment method selection prompt")
    await message.reply_text(
        "💳 Please select your payment method:",
        reply_markup=reply_markup
    )
    logger.info("[ask_payment_method:Return] Returning PAYMENT_METHOD_STATE")
    return PAYMENT_METHOD_STATE

async def handle_payment_method(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[handle_payment_method:Start] Entering handle_payment_method function")
    query = update.callback_query
    message = update.message or update.callback_query.message
    logger.info("[handle_payment_method:AnswerQuery] Answering callback query")
    await query.answer()
    
    logger.info("[handle_payment_method:GetSelectedIndex] Extracting selected payment method index")
    selected_idx = int(query.data.replace("payment_", ""))
    methods = context.user_data["payment_methods"]
    selected_method = methods[selected_idx]
    logger.info(f"[handle_payment_method:SelectedMethod] Selected payment method: {selected_method}")
    
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    logger.info(f"[handle_payment_method:ClickMethod] Clicking payment method: {selected_method}")
    await page.locator(f"div.type:has(p:has-text('{selected_method}')) p").click()
    logger.info("[handle_payment_method:ClickCheckbox] Clicking defaultUncheckedDisabled2 checkbox")
    await page.click('label[for="defaultUncheckedDisabled2"]')
    logger.info("[handle_payment_method:ClickNext] Clicking Next button")
    await page.get_by_role("button", name="Next").click()

    logger.info(f"[handle_payment_method:EditMessage] Updating message with selected method: {selected_method}")
    await query.edit_message_text(text=f"✅ Selected payment method: {selected_method}")
    logger.info("[handle_payment_method:CallGenerateOutput] Calling generate_complete_output function")
    return await generate_complete_output(update, context)

async def generate_complete_output(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[generate_complete_output:Start] Entering generate_complete_output function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    logger.info("[generate_complete_output:SendStatus] Sending status message for data extraction")
    status_msg = await message.reply_text("Extracting application data....")
    page = active_sessions[chat_id]['page']
    logger.info("[generate_complete_output:WaitLoad] Waiting for page to load")
    await page.wait_for_load_state("networkidle")
    logger.info("[generate_complete_output:WaitSelector] Waiting for summary selector")
    await page.wait_for_selector('div.col-md-4.order-md-2.mb-4.mt-5')

    logger.info("[generate_complete_output:GetContent] Retrieving page content")
    content = await page.content()
    logger.info("[generate_complete_output:ParseContent] Parsing content with BeautifulSoup")
    soup = BeautifulSoup(content, 'html.parser')
    logger.info("[generate_complete_output:SelectContainers] Selecting data containers")
    containers = soup.select('div.col-md-4.order-md-2.mb-4.mt-5 ul.list-group.mb-3')

    data = {}
    logger.info("[generate_complete_output:ProcessContainers] Processing containers")
    for container in containers:
        items = container.find_all('li', class_='list-group-item')
        for item in items[1:]:
            left = item.find('h6')
            right = item.find('span') or item.find('strong')
            logger.info("[generate_complete_output:ExtractItem] Extracting item data")
            await status_msg.edit_text("Extracting application data.... PLEASE WAIT")
            if left and right:
                logger.info("[generate_complete_output:StoreItem] Storing item data")
                key = left.get_text(strip=True)
                value = right.get_text(strip=True)
                data[key] = value
    logger.info("[generate_complete_output:ExtractionComplete] Data extraction completed")
    await status_msg.edit_text("All data extracted successfully.")

    logger.info("[generate_complete_output:FormatMessage] Formatting summary message")
    message_t = "📄 *Your ePassport Summary:*\n\n"
    for key, value in data.items():
        message_t += f"*{key}:* {value}\n"

    logger.info("[generate_complete_output:SendSummary] Sending summary message")
    await status_msg.edit_text(message_t, parse_mode="Markdown")
    
    if data.get("Application Number") is None:
        logger.error("[generate_complete_output:NoAppNumber] Application Number not found")
        await message.reply_text("❌ Application Number not found. Please try again.")
        logger.info("[generate_complete_output:Retry] Retrying generate_complete_output")
        return await generate_complete_output(update, context)
    
    logger.info("[generate_complete_output:GetAppNumber] Retrieving application number")
    app_number = data.get("Application Number", None).replace(" ", "_")
    logger.info(f"[generate_complete_output:GenerateFilename] Generating filename: {app_number}.pdf")
    filename = f"{app_number}.pdf"

    logger.info("[generate_complete_output:CallSavePDF] Calling save_pdf function")
    return await save_pdf(update, context, page, filename=filename, app_number=app_number)

async def save_pdf(update: Update, context: ContextTypes.DEFAULT_TYPE, page, filename="output.pdf", app_number=None) -> int:
    logger.info("[save_pdf:Start] Entering save_pdf function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    logger.info("[save_pdf:SendStatus] Sending PDF generation status")
    status_msg = await message.reply_text(" PDF...")
    folder = "filesdownloaded"
    logger.info("[save_pdf:CreateDir] Creating filesdownloaded directory")
    os.makedirs(folder, exist_ok=True)
    
    logger.info("[save_pdf:SavePDF] Saving PDF")
    pdf_path = os.path.join(folder, filename)
    await page.pdf(path=pdf_path)
    logger.info(f"[save_pdf:PDFSaved] PDF saved as {pdf_path}")
    
    try:
        logger.info("[save_pdf:UploadPDF] Uploading PDF to user")
        await status_msg.edit_text("📎 Uploading PDF ...")
        with open(pdf_path, "rb") as pdf_file:
            logger.info("[save_pdf:SendDocument] Sending PDF document")
            await message.reply_document(document=pdf_file, filename=filename, caption="📎 Here is your instruction PDF.")
            logger.info("[save_pdf:CallMainPassportStatus] Calling main_passport_status")
            result = await main_passport_status(update, context, page, app_number)
            if result:
                logger.info("[save_pdf:SendResult] Sending passport status result")
                await message.reply_text(result)

            logger.info("[save_pdf:SendStatusPDF] Sending passport status PDF")
            with open(f"Passport_status_{app_number}.pdf", "rb") as pdf_file:
                await message.reply_document(pdf_file, caption="Your Appointment report is ready.")
        logger.info("[save_pdf:SendDone] Sending completion message")
        await message.reply_text("✅ All done!")
    finally:
        logger.info("[save_pdf:Cleanup] Cleaning up PDF files")
        try:
            if os.path.exists(pdf_path):
                logger.info(f"[save_pdf:DeletePDF] Deleting PDF file {pdf_path}")
                os.remove(pdf_path)
            if os.path.exists(f"Passport_status_{app_number}.pdf"):
                logger.info(f"[save_pdf:DeleteStatusPDF] Deleting status PDF file Passport_status_{app_number}.pdf")
                os.remove(f"Passport_status_{app_number}.pdf")
        except Exception as e:
            logger.error(f"[save_pdf:DeleteError] Error deleting file: {e}")
    
    logger.info("[save_pdf:SendThankYou] Sending thank you message")
    await message.reply_text("Thank you for using the Ethiopian Passport Booking Bot!")
    logger.info("[save_pdf:SendSupport] Sending support contact message")
    await message.reply_text("If you need further assistance, please contact support.")
    logger.info("[save_pdf:CallNewOrCheck] Calling new_or_check function")
    return await new_or_check(update, context)

async def new_or_check(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[new_or_check:Start] Entering new_or_check function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    logger.info("[new_or_check:NavigateStatus] Navigating to Status page")
    await page.click('a[href="/Status"]')
    logger.info("[new_or_check:NavigateRequest] Navigating to request-appointment page")
    await page.click('a[href="/request-appointment"]')
    logger.info("[new_or_check:WaitForCheckbox] Waiting for defaultChecked2 checkbox")
    await page.wait_for_selector("label[for='defaultChecked2']", timeout=30000)
    logger.info("[new_or_check:ClickCheckbox] Clicking defaultChecked2 checkbox")
    await page.click("label[for='defaultChecked2']")
    logger.info("[new_or_check:ClickCard] Clicking card link")
    await page.click(".card--link")
    logger.info("[new_or_check:SendOptions] Sending new or check options")
    await message.reply_text(
        "Please choose an option:",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("📅 new  Appointment", callback_data="new_appointment")],
            [InlineKeyboardButton("🔍 Check Passport Status", callback_data="passport_status")],
            [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
        ])
    )

    logger.info("[new_or_check:Return] Returning AFTER_START state")
    return AFTER_START

async def after_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[after_start:Start] Entering after_start function")
    message = update.message or update.callback_query.message
    query = update.callback_query
    logger.info("[after_start:AnswerQuery] Answering callback query")
    await query.answer()
    
    if query.data == "new_appointment":
        logger.info("[after_start:NewAppointment] Handling new_appointment option")
        return await new_appointment(update, context)
    elif query.data == "passport_status":
        logger.info("[after_start:PassportStatus] Handling passport_status option")
        return await ask_application_number(update, context)
    elif query.data == "help":
        logger.info("[after_start:Help] Handling help option")
        return await help(update, context)
    else:
        logger.error("[after_start:InvalidOption] Invalid option selected")
        await message.reply_text("❌ Invalid option, please try again.")
        logger.info("[after_start:ReturnInvalid] Returning AFTER_START state")
        return AFTER_START

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[start:Start] Entering start function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    logger.info("[start:SendStatus] Sending initializing session message")
    status_msg = await message.reply_text("Initializing session...")
    
    logger.info("[start:CleanupSession] Cleaning up existing session if any")
    if chat_id in active_sessions:
        if 'page' in active_sessions[chat_id]:
            logger.info("[start:ClosePage] Closing existing page")
            await active_sessions[chat_id]['page'].close()
        if 'browser' in active_sessions[chat_id]:
            logger.info("[start:CloseBrowser] Closing existing browser")
            await active_sessions[chat_id]['browser'].close()
        if 'playwright' in active_sessions[chat_id]:
            logger.info("[start:StopPlaywright] Stopping existing playwright")
            await active_sessions[chat_id]['playwright'].stop()
        logger.info("[start:DeleteSession] Deleting session from active_sessions")
        del active_sessions[chat_id]
    
    try:
        logger.info("[start:StartPlaywright] Starting playwright")
        playwright = await async_playwright().start()
        logger.info("[start:LaunchBrowser] Launching browser")
        await status_msg.edit_text("⚡Launching browser...")
        browser = await playwright.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-dev-shm-usage',
                '--single-process',
                '--disable-gpu',
                '--no-zygote'
            ]
        )

        logger.info("[start:CreateContext] Creating new browser context")
        browser_context = await browser.new_context()
        logger.info("[start:CreatePage] Creating new page")
        page = await browser_context.new_page()
        logger.info("[start:SetTimeouts] Setting page timeouts")
        page.set_default_timeout(120000)
        page.set_default_navigation_timeout(120000)
        
        logger.info("[start:Navigate] Navigating to request-appointment page")
        await page.goto("https://www.ethiopianpassportservices.gov.et/request-appointment", wait_until="load")
        
        logger.info("[start:GetTitle] Retrieving page title")
        title = await page.title()
        logger.info(f"[start:PageTitle] Page title: {title}")
        await status_msg.edit_text("⚡Browser launched. Please wait...")
        await status_msg.edit_text("⚡Loading page...")
        
        logger.info("[start:StoreSession] Storing session in active_sessions")
        active_sessions[chat_id] = {
            'playwright': playwright,
            'browser': browser,
            'page': page,
            'last_active': datetime.now()
        }
        
        logger.info("[start:WaitForCheckbox] Waiting for defaultChecked2 checkbox")
        await page.wait_for_selector("label[for='defaultChecked2']", timeout=300000)
        logger.info("[start:ClickCheckbox] Clicking defaultChecked2 checkbox")
        await page.click("label[for='defaultChecked2']")
        logger.info("[start:ClickCard] Clicking card link")
        await page.click(".card--link")
        logger.info("[start:UpdateStatus] Updating status message")
        await status_msg.edit_text("⚡Page loaded. Please wait...")
        
        logger.info("[start:ClearUserData] Clearing user data")
        context.user_data.clear()
        
        logger.info("[start:SendWelcome] Sending welcome message")
        await status_msg.edit_text("Welcome to the Ethiopian Passport Booking Bot!")
        logger.info("[start:SendOptions] Sending main menu options")
        await message.reply_text(
            "Please choose an option:",
            reply_markup=InlineKeyboardMarkup([
                [InlineKeyboardButton("📅 Book Appointment", callback_data="book_appointment")],
                [InlineKeyboardButton("🔍 Check Passport Status", callback_data="passport_status")],
                [InlineKeyboardButton("ℹ️ Help", callback_data="help")]
            ])
        )

        logger.info("[start:Return] Returning MAIN_MENU state")
        return MAIN_MENU
    except Exception as e:
        logger.error(f"[start:Error] Error initializing session: {str(e)}")
        await message.reply_text(f"❌ Error initializing session: {str(e)}")
        logger.info("[start:ReturnError] Returning ConversationHandler.END")
        return ConversationHandler.END

async def main_menu_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[main_menu_handler:Start] Entering main_menu_handler function")
    query = update.callback_query
    logger.info("[main_menu_handler:AnswerQuery] Answering callback query")
    await query.answer()
    chat_id = query.message.chat.id
    
    logger.info("[main_menu_handler:UpdateLastActive] Updating last active time")
    if chat_id in active_sessions:
        active_sessions[chat_id]['last_active'] = datetime.now()
    
    if query.data == "book_appointment":
        logger.info("[main_menu_handler:BookAppointment] Handling book_appointment option")
        await query.edit_message_text(text="📅 Booking an appointment...")
        logger.info("[main_menu_handler:CallNewAppointment] Calling new_appointment function")
        return await new_appointment(update, context)
    elif query.data == "passport_status":
        logger.info("[main_menu_handler:PassportStatus] Handling passport_status option")
        await query.edit_message_text(text="🔍 Checking passport status...")
        logger.info("[main_menu_handler:CallAskApplicationNumber] Calling ask_application_number function")
        return await ask_application_number(update, context)
    elif query.data == "help":
        logger.info("[main_menu_handler:Help] Handling help option")
        logger.info("[main_menu_handler:CallHelp] Calling help function")
        return await help(update, context)
    else:   
        logger.error("[main_menu_handler:InvalidOption] Invalid option selected")
        await query.edit_message_text(text="❌ Invalid option, please try again.")
        logger.info("[main_menu_handler:ReturnInvalid] Returning MAIN_MENU state")
        return MAIN_MENU

async def new_appointment(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[new_appointment:Start] Entering new_appointment function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    
    if chat_id not in active_sessions:
        logger.error("[new_appointment:SessionExpired] Session expired")
        await message.reply_text("❌ Session expired. Please /start again.")
        logger.info("[new_appointment:ReturnExpired] Returning ConversationHandler.END")
        return ConversationHandler.END
    
    try:
        logger.info("[new_appointment:ResetDropdown] Resetting dropdown step")
        context.user_data["dropdown_step"] = 0
        page = active_sessions[chat_id]['page']
        logger.info("[new_appointment:UpdateLastActive] Updating last active time")
        active_sessions[chat_id]['last_active'] = datetime.now()
        
        logger.info("[new_appointment:WaitLoad] Waiting for page to load")
        await page.wait_for_load_state('networkidle')
        logger.info("[new_appointment:WaitSelector] Waiting for teal card selector")
        await page.wait_for_selector(".card--teal.flex.flex--column", state='visible', timeout=60000)
        
        logger.info("[new_appointment:ClickCard] Clicking teal card")
        await page.evaluate('''() => {
            document.querySelector('.card--teal.flex.flex--column').click();
        }''')
        
        logger.info("[new_appointment:SendReady] Sending ready message")
        await message.reply_text("✅ Ready! Let's begin your appointment booking.")
        logger.info("[new_appointment:CallAskRegion] Calling ask_region function")
        return await ask_region(update, context)
    except Exception as e:
        logger.error(f"[new_appointment:Error] Error starting appointment: {str(e)}")
        await message.reply_text(f"❌ Error starting appointment: {str(e)}")
        logger.info("[new_appointment:CallMainMenu] Calling main_menu_handler function")
        return await main_menu_handler(update, context)

async def main_passport_status(update: Update, context: ContextTypes.DEFAULT_TYPE, page, application_number) -> str:
    logger.info("[main_passport_status:Start] Entering main_passport_status function")
    message = update.message or update.callback_query.message
    logger.info("[main_passport_status:SendStatus] Sending status page loading message")
    status_msg = await message.reply_text("Loading status page...")
    logger.info("[main_passport_status:ClickStatus] Clicking Status link")
    await page.click('a[href="/Status"]')
    logger.info("[main_passport_status:UpdateStatus] Updating status message")
    await status_msg.edit_text("⚡Page loaded. Please wait...")
    logger.info("[main_passport_status:WaitForInput] Waiting for application number input")
    await page.wait_for_selector('input[placeholder="Application Number"]', timeout=5000)
    logger.info("[main_passport_status:UpdateStatusInput] Updating status for filling application number")
    await status_msg.edit_text("Filling application number...")
    logger.info(f"[main_passport_status:FillInput] Filling application number: {application_number}")
    await page.fill('input[placeholder="Application Number"]', application_number)
    logger.info("[main_passport_status:UpdateStatusCheck] Updating status for checking data")
    await status_msg.edit_text("checking data...")

    logger.info("[main_passport_status:ClickSearch] Clicking Search button")
    await page.click('button:has-text("Search")')
    logger.info("[main_passport_status:WaitAfterSearch] Waiting after clicking Search")
    await page.wait_for_timeout(5000)
    
    logger.info("[main_passport_status:CheckDataNotFound] Checking for data not found message")
    if await page.locator('text=Data not Found. Please Make sure You have Paid the Request.').is_visible():
        logger.error("[main_passport_status:DataNotFound] Invalid Application Number")
        await status_msg.edit_text("❌ Invalid Application Number. Please try again.")
        logger.info("[main_passport_status:CallAskApplicationNumber] Calling ask_application_number function")
        return await ask_application_number(update, context)  

    logger.info("[main_passport_status:WaitForCard] Waiting for card link selector")
    await page.wait_for_selector('a.card--link', timeout=5000)
    logger.info("[main_passport_status:GetCard] Retrieving card link element")
    card = await page.query_selector('a.card--link')
    logger.info("[main_passport_status:GetCardText] Extracting card text content")
    text_content = await card.inner_text()
    logger.info("[main_passport_status:FindEyeButton] Locating eye button")
    eye_button = await card.query_selector('div i.fa-eye')
    if eye_button:
        logger.info("[main_passport_status:ClickEyeButton] Clicking eye button")
        await eye_button.click()
    else:
        logger.error("[main_passport_status:NoEyeButton] Eye icon not found")
        await status_msg.edit_text("❌ Invalid Application Number. Please try again.")
        logger.info("[main_passport_status:CallAskApplicationNumberNoEye] Calling ask_application_number function")
        return await ask_application_number(update, context)

    logger.info("[main_passport_status:WaitAfterEyeClick] Waiting after clicking eye button")
    await page.wait_for_timeout(3000)
    logger.info("[main_passport_status:UpdateStatusPDF] Updating status for PDF generation")
    await status_msg.edit_text("Generating PDF...")
    logger.info("[main_passport_status:CallGeneratePDF] Calling generate_official_pdf function")
    await generate_official_pdf(page, application_number)
    logger.info("[main_passport_status:UpdateStatusComplete] Updating status for PDF completion")
    await status_msg.edit_text("PDF generated successfully.")
    logger.info("[main_passport_status:ReturnText] Returning extracted text content")
    return text_content.strip()

async def generate_official_pdf(page, application_number):
    logger.info("[generate_official_pdf:Start] Entering generate_official_pdf function")
    logger.info(f"[generate_official_pdf:SavePDF] Saving PDF for application number: {application_number}")
    await page.pdf(
        path=f"Passport_status_{application_number}.pdf",
        print_background=True,
    )
    logger.info("[generate_official_pdf:PDFSaved] PDF saved successfully")

async def ask_application_number(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[ask_application_number:Start] Entering ask_application_number function")
    message = update.message or update.callback_query.message
    logger.info("[ask_application_number:ReplyText] Sending application number prompt")
    await message.reply_text("Please enter your Application Number to get started.")
    logger.info("[ask_application_number:Return] Returning state 111")
    return 111

async def passport_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[passport_status:Start] Entering passport_status function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    page = active_sessions[chat_id]['page']
    logger.info("[passport_status:GetPassportNumber] Retrieving passport number from message")
    passport_number = message.text
    logger.info(f"[passport_status:CallMainPassportStatus] Calling main_passport_status with number: {passport_number}")
    result = await main_passport_status(update, context, page, passport_number)
    if result:
        try:
            logger.info("[passport_status:SendResult] Sending passport status result")
            await message.reply_text(result)
            logger.info(f"[passport_status:OpenPDF] Opening status PDF for number: {passport_number}")
            with open(f"Passport_status_{passport_number}.pdf", "rb") as pdf_file:
                logger.info("[passport_status:SendPDF] Sending passport status PDF")
                await message.reply_document(pdf_file, caption="Your passport status report is ready.")
                logger.info("[passport_status:SendDone] Sending completion message")
                await message.reply_text("✅ All done!")
                logger.info("[passport_status:CallNewOrCheck] Calling new_or_check function")
                return await new_or_check(update, context)
        except FileNotFoundError:
            logger.error(f"[passport_status:FileNotFound] File Passport_status_{passport_number}.pdf not found")
        finally:
            try:
                logger.info("[passport_status:Cleanup] Cleaning up status PDF")
                if os.path.exists(f"Passport_status_{passport_number}.pdf"):
                    logger.info(f"[passport_status:DeletePDF] Deleting file Passport_status_{passport_number}.pdf")
                    os.remove(f"Passport_status_{passport_number}.pdf")
            except Exception as e:
                logger.error(f"[passport_status:DeleteError] Error deleting file: {e}")
    logger.info("[passport_status:Retry] Retrying passport_status function")
    return await passport_status(update, context)

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[cancel:Start] Entering cancel function")
    message = update.message or update.callback_query.message
    chat_id = message.chat.id
    
    logger.info("[cancel:CleanupSession] Cleaning up browser session")
    if chat_id in active_sessions:
        if 'page' in active_sessions[chat_id]:
            logger.info("[cancel:ClosePage] Closing page")
            await active_sessions[chat_id]['page'].close()
        if 'browser' in active_sessions[chat_id]:
            logger.info("[cancel:CloseBrowser] Closing browser")
            await active_sessions[chat_id]['browser'].close()
        if 'playwright' in active_sessions[chat_id]:
            logger.info("[cancel:StopPlaywright] Stopping playwright")
            await active_sessions[chat_id]['playwright'].stop()
        logger.info("[cancel:DeleteSession] Deleting session from active_sessions")
        del active_sessions[chat_id]
    
    logger.info("[cancel:ClearUserData] Clearing user data")
    context.user_data.clear()
    
    logger.info("[cancel:ReplyText] Sending cancellation message")
    await message.reply_text("❌ Operation cancelled. Starting over...")
    logger.info("[cancel:CallStart] Calling start function")
    await start(update, context)
    logger.info("[cancel:Return] Returning ConversationHandler.END")
    return ConversationHandler.END

async def help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    logger.info("[help:Start] Entering help function")
    message = update.message or update.callback_query.message
    logger.info("[help:CreateKeyboard] Creating help menu keyboard")
    keyboard = [
        [InlineKeyboardButton("Book Appointment", callback_data="help_book")],
        [InlineKeyboardButton("Check Status", callback_data="help_status")],
        [InlineKeyboardButton("Cancel Appointment", callback_data="help_cancel")],
        [InlineKeyboardButton("Contact Support", callback_data="help_contact")]
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    logger.info("[help:SendPrompt] Sending help menu prompt")
    await message.reply_text(
        "I can help you with the following:",
        reply_markup=reply_markup
    )
    logger.info("[help:Return] Returning HELP_MENU state")
    return HELP_MENU

async def handle_help(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.info("[handle_help:Start] Entering handle_help function")
    query = update.callback_query
    logger.info("[handle_help:AnswerQuery] Answering callback query")
    await query.answer()
    
    if query.data == "help_book":
        logger.info("[handle_help:HelpBook] Handling help_book option")
        await query.edit_message_text(text="To book an appointment, use the new appointment button.\n\nFollow the prompts to select your region, city, and other details.\n\nplease make sure to have your documents ready.")
    elif query.data == "help_status":
        logger.info("[handle_help:HelpStatus] Handling help_status option")
        await query.edit_message_text(text="To check your passport status, use the check status button. \n\nEnter your application number when prompted.")
    elif query.data == "help_cancel":
        logger.info("[handle_help:HelpCancel] Handling help_cancel option")
        await query.edit_message_text(text="To cancel your appointment, use the /cancel command. \n\nThis will clear your current session and start over.")
    elif query.data == "help_contact":
        logger.info("[handle_help:HelpContact] Handling help_contact option")
        await query.edit_message_text(text="For support, please contact us at t.me/ns_asharama")
    logger.info("[handle_help:Return] Returning ConversationHandler.END")
    return ConversationHandler.END

async def cleanup_inactive_sessions():
    logger.info("[cleanup_inactive_sessions:Start] Entering cleanup_inactive_sessions function")
    while True:
        try:
            logger.info("[cleanup_inactive_sessions:CheckSessions] Checking for inactive sessions")
            now = datetime.now()
            for chat_id in list(active_sessions.keys()):
                try:
                    logger.info(f"[cleanup_inactive_sessions:CheckChat] Checking session for chat_id {chat_id}")
                    last_active = active_sessions[chat_id].get('last_active')
                    if last_active and now - last_active > timedelta(minutes=30):
                        logger.info(f"[cleanup_inactive_sessions:InactiveFound] Found inactive session for chat_id {chat_id}")
                        if 'page' in active_sessions[chat_id]:
                            logger.info(f"[cleanup_inactive_sessions:ClosePage] Closing page for chat_id {chat_id}")
                            await active_sessions[chat_id]['page'].close()
                        if 'browser' in active_sessions[chat_id]:
                            logger.info(f"[cleanup_inactive_sessions:CloseBrowser] Closing browser for chat_id {chat_id}")
                            await active_sessions[chat_id]['browser'].close()
                        if 'playwright' in active_sessions[chat_id]:
                            logger.info(f"[cleanup_inactive_sessions:StopPlaywright] Stopping playwright for chat_id {chat_id}")
                            await active_sessions[chat_id]['playwright'].stop()
                        logger.info(f"[cleanup_inactive_sessions:DeleteSession] Deleting session for chat_id {chat_id}")
                        del active_sessions[chat_id]
                except Exception as e:
                    logger.error(f"[cleanup_inactive_sessions:SessionError] Error cleaning up session for chat_id {chat_id}: {e}")
            logger.info("[cleanup_inactive_sessions:Sleep] Sleeping for 5 minutes")
            await asyncio.sleep(300)
        except asyncio.CancelledError:
            logger.info("[cleanup_inactive_sessions:Cancelled] Cleanup task cancelled")
            break
        except Exception as e:
            logger.error(f"[cleanup_inactive_sessions:Error] Error in cleanup task: {e}")
            logger.info("[cleanup_inactive_sessions:SleepRetry] Sleeping for 1 minute before retry")
            await asyncio.sleep(60)

if __name__ == "__main__":
    logger.info("[main:Start] Starting application")
    application = Application.builder() \
        .token(TELEGRAM_BOT_TOKEN) \
        .read_timeout(300) \
        .write_timeout(300) \
        .connect_timeout(300) \
        .pool_timeout(300) \
        .build()
    logger.info("[main:ApplicationBuilt] Application built successfully")

    async def error_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
        logger.info("[error_handler:Start] Entering error_handler function")
        error = context.error
        if isinstance(error, Exception):
            logger.error(f"[error_handler:LogError] An error occurred: {error}")
        
        if update and update.effective_message:
            logger.info("[error_handler:SendErrorMessage] Sending error message to user")
            await update.effective_message.reply_text(
                "🔧 System encountered an error. Please /start again.\n"
                f"Error reference: {hash(str(error))}"
            )
        logger.info("[error_handler:End] Exiting error_handler function")

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
        per_message=False,
        per_user=True,
        per_chat=True,
    )
    logger.info("[main:MainMenuHandler] Main menu conversation handler configured")

    check_status = ConversationHandler(
        entry_points=[
            CommandHandler("passport_status", ask_application_number),
            CallbackQueryHandler(ask_application_number, pattern="^passport_status")
        ],
        states={
            111: [MessageHandler(filters.TEXT & ~filters.COMMAND, passport_status)],
            AFTER_START: [
                CallbackQueryHandler(after_start, pattern="^new_appointment"),
                CallbackQueryHandler(after_start, pattern="^passport_status"),
                CallbackQueryHandler(after_start, pattern="^help")
            ]
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        per_user=True,
        per_chat=True,
    )
    logger.info("[main:CheckStatusHandler] Check status conversation handler configured")

    form_handle = ConversationHandler(
        entry_points=[
            CommandHandler("new_appointment", new_appointment),
            CallbackQueryHandler(new_appointment, pattern="^book_appointment")
        ],
        states={
            0: [CallbackQueryHandler(ask_region_response, pattern="^region_")],
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
            111: [MessageHandler(filters.TEXT & ~filters.COMMAND, passport_status)],
            HELP_MENU: [CallbackQueryHandler(handle_help, pattern="^help_")],
            MAIN_MENU: [
                CallbackQueryHandler(main_menu_handler)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
        per_message=False,
        per_user=True,
        per_chat=True,
    )
    logger.info("[main:FormHandler] Form conversation handler configured")

    help_h = ConversationHandler(
        entry_points=[
            CommandHandler("help", help),
            CallbackQueryHandler(help, pattern="^help")
        ],
        states={
            HELP_MENU: [CallbackQueryHandler(handle_help, pattern="^help_")]
        },
        fallbacks=[CommandHandler("cancel", cancel)]
    )
    logger.info("[main:HelpHandler] Help conversation handler configured")

    logger.info("[main:AddHandlers] Adding handlers to application")
    application.add_handler(CommandHandler("start", start))
    application.add_handler(form_handle)
    application.add_handler(check_status)
    application.add_handler(help_h)
    application.add_handler(CommandHandler("cancel", cancel))

    async def post_init(application):
        logger.info("[post_init:Start] Entering post_init function")
        logger.info("[post_init:CreateCleanupTask] Creating cleanup_inactive_sessions task")
        asyncio.create_task(cleanup_inactive_sessions())
        logger.info("[post_init:End] Exiting post_init function")

    logger.info("[main:SetPostInit] Setting post_init function")
    application.post_init = post_init
    logger.info("[main:RunPolling] Starting application polling")
    application.run_polling()