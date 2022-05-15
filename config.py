import logging
import os


ADMIN_ID = os.environ["ADMIN_ID"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
KITTEN_SOURCE = os.environ["KITTEN_SOURCE"]
DATABASE_URL = os.environ["DATABASE_URL"].replace("postgres://", "postgresql://")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO)

LOGGER = logging.getLogger(__name__)

