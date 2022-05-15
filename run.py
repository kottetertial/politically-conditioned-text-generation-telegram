import io
from csv import DictReader

import requests
from sqlalchemy import func, nullsfirst
from sqlalchemy.orm import sessionmaker
from telegram import Update, ReplyKeyboardMarkup, \
    ReplyKeyboardRemove, File
from telegram.ext import Application, CallbackContext, CommandHandler, MessageHandler, filters, ConversationHandler

from config import BOT_TOKEN, DATABASE_URL, KITTEN_SOURCE
from db import start_database, session_scope
from model import Item, Interaction
from utils import admin_tool

EXPECT_READY, EXPECT_RELEVANCE, EXPECT_QUALITY, START_AGAIN, HERO = range(5)
EVALUATION_KEYBOARD = [["1", "2", "3", "4", "5", "Cancel"]]
YES_NO_KEYBOARD = [["Yes", "No"]]
TEXT_FORMAT = "<b>Tag</b>: {}\n<b>Text</b>: {}"


async def start(update: Update, context: CallbackContext.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html(rf"Hi {user.mention_html()}!")
    await help_command(update, context)


async def help_command(update: Update, context: CallbackContext.DEFAULT_TYPE) -> None:
    await update.message.reply_text("Use the /get_text command to start evaluating texts.")


@admin_tool
async def add_items(update: Update, context: CallbackContext.DEFAULT_TYPE) -> None:
    file: File = await update.message.document.get_file()
    filebytes: bytearray = await file.download_as_bytearray()
    filestring: str = filebytes.decode(encoding="utf-8", errors="ignore")
    reader: DictReader = DictReader(io.StringIO(filestring), delimiter="\t")

    await update.message.reply_text("Started uploading new items...")
    failure_reply: str = "An error occurred. Please see the logs."

    async with session_scope(Session, update, failure_reply) as session:
        counter: int = 0
        for i in reader:
            counter += 1
            item = Item(
                label=i["Class"],
                content=i["Text"]
            )
            session.add(item)
        await update.message.reply_text(f"Successfully uploaded {counter} items!")


async def get_text(update: Update, context: CallbackContext.DEFAULT_TYPE) -> int:
    user = update.message.from_user

    async with session_scope(Session) as session:
        texts_evaluated = session\
            .query(Interaction.item_id)\
            .filter_by(user_id=user.id)

        evaluation_per_text = session\
            .query(Interaction.item_id, func.count().label("cnt"))\
            .group_by(Interaction.item_id).subquery()

        text_evaluation_count = session\
            .query(Item.id, evaluation_per_text.c.cnt.label("cnt"))\
            .join(evaluation_per_text,
                  Item.id == evaluation_per_text.c.item_id,
                  isouter=True).subquery()

        text_to_evaluate = session\
            .query(Item)\
            .join(text_evaluation_count,
                  Item.id == text_evaluation_count.c.id,
                  isouter=True)\
            .filter(Item.id.not_in(texts_evaluated))\
            .order_by(nullsfirst(text_evaluation_count.c.cnt))\
            .limit(1)\
            .first()

        if not text_to_evaluate:
            context.user_data["hero"] = "Looks like you've evaluated all available texts! I'm very grateful for your " \
                                        "help. Feel free to come back later for new ones. Get the kitten for now :)"
            await kitten(update, context)
            context.user_data.clear()
            return ConversationHandler.END

        context.user_data["item_id"] = text_to_evaluate.id
        await update.message.reply_text(TEXT_FORMAT.format(text_to_evaluate.label, text_to_evaluate.content),
                                        parse_mode="html",
                                        reply_markup=ReplyKeyboardMarkup([["Evaluate"]],
                                                                         resize_keyboard=True))
        return EXPECT_READY


async def kitten(update: Update, context: CallbackContext.DEFAULT_TYPE) -> None:
    kitten_response = requests.get(KITTEN_SOURCE)
    kitten_picture = io.BufferedReader(io.BytesIO(kitten_response.content))

    await update.message.reply_photo(kitten_picture,
                                     caption=context.user_data.get("hero"))


async def ready_button_click(update: Update, context: CallbackContext.DEFAULT_TYPE) -> int:
    await update.message.reply_text("How relevant is the text to the tag?",
                                    reply_markup=ReplyKeyboardMarkup(
                                        EVALUATION_KEYBOARD,
                                        resize_keyboard=True
                                    ))
    return EXPECT_RELEVANCE


async def evaluate_relevance(update: Update, context: CallbackContext.DEFAULT_TYPE) -> int:
    context.user_data["relevance"] = update.message.text
    await update.message.reply_text("How understandable and correct is the text?",
                                    reply_markup=ReplyKeyboardMarkup(
                                        EVALUATION_KEYBOARD,
                                        one_time_keyboard=True,
                                        resize_keyboard=True
                                    ))
    return EXPECT_QUALITY


async def evaluate_quality(update: Update, context: CallbackContext.DEFAULT_TYPE) -> int:
    user_id = update.message.from_user.id
    item_id = context.user_data.get("item_id")
    relevance = context.user_data.get("relevance")
    quality = update.message.text

    async with session_scope(Session) as session:
        interaction = Interaction(
            user_id=user_id,
            item_id=item_id,
            relevance=relevance,
            quality=quality
        )
        session.add(interaction)

        await update.message.reply_text("Thank you for your response! Would you like to evaluate another text?",
                                        reply_markup=ReplyKeyboardMarkup(
                                            YES_NO_KEYBOARD,
                                            one_time_keyboard=True,
                                            resize_keyboard=True
                                        ))
        return START_AGAIN


async def cancel(update: Update, context: CallbackContext.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Thank you for your participation!",
                                    reply_markup=ReplyKeyboardRemove())
    context.user_data.clear()
    return ConversationHandler.END


def main() -> None:
    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(MessageHandler(filters.Document.FileExtension("tsv"), add_items))
    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler("get_text", get_text)],
        states={
            EXPECT_READY: [MessageHandler(filters.Regex("[eE]valuate"), ready_button_click)],
            EXPECT_RELEVANCE: [MessageHandler(filters.Regex(r"\d{1}"), evaluate_relevance)],
            EXPECT_QUALITY: [MessageHandler(filters.Regex(r"\d{1}"), evaluate_quality)],
            START_AGAIN: [MessageHandler(filters.Regex("[yY]es"), get_text),
                          MessageHandler(filters.Regex("[nN]o"), cancel)]
        },
        fallbacks=[CommandHandler("cancel", cancel),
                   MessageHandler(filters.Regex("[cC]ancel"), cancel)]
    ))
    application.add_handler(CommandHandler("kitten", kitten))

    application.run_polling()


if __name__ == "__main__":
    Session: sessionmaker = start_database(DATABASE_URL)
    main()
