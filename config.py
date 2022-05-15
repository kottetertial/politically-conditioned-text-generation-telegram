import logging
import os
from dotenv import load_dotenv


load_dotenv()


ADMIN_ID = os.getenv("ADMIN_ID")
BOT_TOKEN = os.getenv("BOT_TOKEN")
KITTEN_SOURCE = os.getenv("KITTEN_SOURCE")
DATABASE_URL = os.getenv("POSTGRES_URL").replace("postgres://", "postgresql://")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO)

LOGGER = logging.getLogger(__name__)

