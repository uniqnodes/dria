import logging
import requests
from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ConversationHandler, CallbackContext

TOKEN = "YOUR_TELEGRAM_BOT_TOKEN"

# Logging settings
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# Conversation states
NODE_ID, INTERVAL = range(2)

# URL to fetch JSON data
BASE_URL = "https://dkn.dria.co/dashboard/supply/v0/leaderboard/steps?address="

# Time interval options
TIME_OPTIONS = [['6 hours', '12 hours'], ['24 hours']]

async def start(update: Update, context: CallbackContext) -> int:
    await update.message.reply_text(
        "Hello! Please enter your Node ID:",
        reply_markup=ReplyKeyboardRemove()
    )
    return NODE_ID

async def node_id(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    context.user_data['node_id'] = update.message.text
    logger.info("Node ID of %s: %s", user.first_name, update.message.text)

    await update.message.reply_text(
        "How often would you like to receive reports?",
        reply_markup=ReplyKeyboardMarkup(TIME_OPTIONS, one_time_keyboard=True, resize_keyboard=True)
    )
    return INTERVAL

async def interval(update: Update, context: CallbackContext) -> int:
    user = update.message.from_user
    interval_input = update.message.text

    # Validate the interval input
    if interval_input not in ['6 hours', '12 hours', '24 hours']:
        await update.message.reply_text(
            "Invalid interval! Please choose from '6 hours', '12 hours', or '24 hours'.",
            reply_markup=ReplyKeyboardMarkup(TIME_OPTIONS, one_time_keyboard=True, resize_keyboard=True)
        )
        return INTERVAL  # Return to the interval selection step

    context.user_data['interval'] = interval_input
    logger.info("Interval chosen by %s: %s", user.first_name, interval_input)

    # Stop the old job if it exists
    if 'job' in context.user_data:
        context.user_data['job'].schedule_removal()

    # Convert interval to seconds
    if interval_input == '6 hours':
        interval_seconds = 21600
    elif interval_input == '12 hours':
        interval_seconds = 43200
    elif interval_input == '24 hours':
        interval_seconds = 86400

    # Start the new job
    job = context.job_queue.run_repeating(
        send_report,  # Function to run
        interval=interval_seconds,  # Interval in seconds
        first=0,  # First run time (0 = immediately)
        chat_id=update.message.chat_id,  # Chat ID
        data=context.user_data['node_id']  # Node ID as data
    )
    context.user_data['job'] = job  # Save the job

    await update.message.reply_text(
        f"Setup complete! You will receive reports every {interval_input}.",
        reply_markup=ReplyKeyboardRemove()
    )

    # Send the first report immediately
    await send_report_immediately(update, context)

    # Show the menu
    await menu(update, context)

    return ConversationHandler.END

async def send_report_immediately(update: Update, context: CallbackContext) -> None:
    """Send a report immediately to the user."""
    node_id = context.user_data['node_id']
    url = BASE_URL + node_id
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            message = f"Percentile: {data.get('percentile', 'N/A')}\nScore: {data.get('score', 'N/A')}"
            await update.message.reply_text(message)
        else:
            await update.message.reply_text("Failed to fetch data.")
    except Exception as e:
        logger.error(f"Error while sending report: {e}")
        await update.message.reply_text("An error occurred while sending the report.")

async def send_report(context: CallbackContext) -> None:
    """Send a report at the specified interval."""
    node_id = context.job.data  # Get Node ID from job data
    chat_id = context.job.chat_id  # Get chat ID
    url = BASE_URL + node_id
    try:
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            message = f"Percentile: {data.get('percentile', 'N/A')}\nScore: {data.get('score', 'N/A')}"
            await context.bot.send_message(chat_id=chat_id, text=message)
        else:
            await context.bot.send_message(chat_id=chat_id, text="Failed to fetch data.")
    except Exception as e:
        logger.error(f"Error while sending report: {e}")

async def menu(update: Update, context: CallbackContext) -> None:
    """Show the menu options to the user without any text."""
    menu_options = [['New Report']]
    await update.message.reply_text(
        "-",  # Empty string to avoid displaying any text
        reply_markup=ReplyKeyboardMarkup(menu_options, one_time_keyboard=True, resize_keyboard=True)
    )

async def handle_menu(update: Update, context: CallbackContext) -> None:
    """Handle menu options."""
    choice = update.message.text
    if choice == 'New Report':
        await send_report_immediately(update, context)

async def cancel(update: Update, context: CallbackContext) -> int:
    """Cancel the conversation."""
    user = update.message.from_user
    logger.info("User %s canceled the conversation.", user.first_name)
    await update.message.reply_text("Operation canceled.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def main() -> None:
    # Replace with your bot token
    application = Application.builder().token(TOKEN).build()

    # Conversation handler
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler('start', start)],
        states={
            NODE_ID: [MessageHandler(filters.TEXT & ~filters.COMMAND, node_id)],
            INTERVAL: [MessageHandler(filters.TEXT & ~filters.COMMAND, interval)],
        },
        fallbacks=[CommandHandler('cancel', cancel)],
    )

    # Menu handler
    application.add_handler(MessageHandler(filters.Text(['New Report']), handle_menu))
    application.add_handler(CommandHandler('menu', menu))

    application.add_handler(conv_handler)

    # Start the bot
    application.run_polling()

if __name__ == '__main__':
    main()
