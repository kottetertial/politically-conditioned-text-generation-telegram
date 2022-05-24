import csv
import io
from csv import DictReader
from typing import Tuple, List, Dict

import requests
from sqlalchemy import func, nullsfirst
from sqlalchemy.orm import sessionmaker
from telegram import Update, ReplyKeyboardMarkup, \
    ReplyKeyboardRemove, File
from telegram.ext import Application, CallbackContext, CommandHandler, MessageHandler, filters, ConversationHandler

from config import BOT_TOKEN, DATABASE_URL, KITTEN_SOURCE
from db import start_database, session_scope, clear_database, get_all_data
from model import Item, Interaction
from utils import admin_tool


EXPECT_READY, EXPECT_RELEVANCE, EXPECT_QUALITY, START_AGAIN, CONFIRM_DROP = range(5)
EVALUATION_KEYBOARD = [["1", "2", "3", "4", "5", "Cancel"]]
YES_NO_KEYBOARD = [["Yes", "No"]]
TEXT_FORMAT = "<b>Tag</b>: {}\n<b>Text</b>: {}"
FAILURE_REPLY = "An error occurred. Please see the logs."


async def start(update: Update, context: CallbackContext.DEFAULT_TYPE) -> None:
    user = update.effective_user
    await update.message.reply_html("Hi {}! "
                                    "\nTo get more info about the project, use the /help command. "
                                    "\nTo start evaluating texts, use the /get_text command.".format(user.full_name))


async def help_command(update: Update, context: CallbackContext.DEFAULT_TYPE) -> None:
    await update.message.reply_text("This is a tool developed as part of an NLP project. "
                                    "The aim of the project is to devise a model to automatically generate "
                                    "politically-conditioned texts. That is, texts produced my the model are supposed "
                                    "to somehow reflect political views of a person "
                                    "who identifies as a liberal or a conservative. "
                                    "The political leaning is defined by the user "
                                    "and the model is supposed to generate some text relevant to the condition. "
                                    "\n\nThe purpose of this tool is to evaluate the produced texts "
                                    "in terms of their quality (fluency) and relevance to the condition. "
                                    "Both parameters are evaluated from 1 to 5, "
                                    "where 1 means not fluent/relevant at all, "
                                    "and 5 stands for very fluent/very relevant. "
                                    "\n\nYou are kindly asked to take part in the evaluation! "
                                    "\n\nUse the /get_text command to get a text produced by the model "
                                    "and the tag it was generated under. "
                                    "After that, you will be prompted to start the evaluation.")


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


@admin_tool
async def add_items(update: Update, context: CallbackContext.DEFAULT_TYPE) -> None:
    file: File = await update.message.document.get_file()
    filebytes: bytearray = await file.download_as_bytearray()
    filestring: str = filebytes.decode(encoding="utf-8", errors="ignore")
    reader: DictReader = DictReader(io.StringIO(filestring), delimiter="\t")

    await update.message.reply_text("Started uploading new items...")

    async with session_scope(Session, update, FAILURE_REPLY) as session:
        counter: int = 0
        for i in reader:
            counter += 1
            item = Item(
                label=i["Class"],
                content=i["Text"]
            )
            session.add(item)

    await update.message.reply_text(f"Successfully uploaded {counter} items!")


@admin_tool
async def export_all(update: Update, context: CallbackContext.DEFAULT_TYPE) -> None:
    async with session_scope(Session, update, FAILURE_REPLY) as session:
        data: Dict[str, List[Tuple]] = get_all_data(session)

    for tablename, content in data.items():
        sio: io.StringIO = io.StringIO()
        writer: csv.writer = csv.writer(sio)
        writer.writerows(map(lambda x: x[1:], content))
        sio.seek(0)

        bytefile: io.BytesIO = io.BytesIO(sio.getvalue().encode(encoding="utf-8", errors="ignore"))
        document: io.BufferedReader = io.BufferedReader(bytefile)

        await update.message.reply_document(document,
                                            f"{tablename}.csv")


@admin_tool
async def drop_all(update: Update, context: CallbackContext.DEFAULT_TYPE) -> int:
    await update.message.reply_text("Are you sure you want to delete all data?",
                                    reply_markup=ReplyKeyboardMarkup(
                                        YES_NO_KEYBOARD,
                                        resize_keyboard=True
                                    ))
    return CONFIRM_DROP


@admin_tool
async def drop_all_confirmed(update: Update, context: CallbackContext.DEFAULT_TYPE) -> int:
    async with session_scope(Session) as session:
        clear_database(session)
        await update.message.reply_text("Successfully cleared all data!",
                                        reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END


DEFAULT_FALLBACKS = [CommandHandler("cancel", cancel), MessageHandler(filters.Regex("[cC]ancel"), cancel)]


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
        fallbacks=DEFAULT_FALLBACKS
    ))
    application.add_handler(CommandHandler("kitten", kitten))
    application.add_handler(ConversationHandler(
        entry_points=[CommandHandler("drop_all", drop_all)],
        states={
            CONFIRM_DROP: [MessageHandler(filters.Regex("[yY]es"), drop_all_confirmed)]
        },
        fallbacks=DEFAULT_FALLBACKS
    ))
    application.add_handler(CommandHandler("export_all", export_all))

    application.run_polling()


if __name__ == "__main__":
    Session: sessionmaker = start_database(DATABASE_URL)
    main()
