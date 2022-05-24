from contextlib import asynccontextmanager
from typing import Optional, List, Tuple, Dict

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base, Session
from telegram import Update

from config import LOGGER
from model import Base


def start_database(url: str, base: declarative_base = Base) -> sessionmaker:
    engine = create_engine(url)
    base.metadata.create_all(engine)
    return sessionmaker(bind=engine)


def get_all_data(session: Session, base: declarative_base = Base) -> Dict[str, List[Tuple]]:
    container: Dict[str, List[Tuple]] = dict()
    for table in base.metadata.sorted_tables:
        container[table.fullname] = session.query(table).all()
    return container


def clear_database(session: Session, base: declarative_base = Base) -> None:
    for table in reversed(base.metadata.sorted_tables):
        session.execute(table.delete())


@asynccontextmanager
async def session_scope(session_maker: sessionmaker,
                        update: Optional[Update] = None,
                        fallback_message: Optional[str] = None):
    session = session_maker()
    try:
        yield session
        session.commit()
    except Exception:
        if update and fallback_message:
            await update.message.reply_text(fallback_message)
        LOGGER.exception()
        session.rollback()
    finally:
        session.close()
