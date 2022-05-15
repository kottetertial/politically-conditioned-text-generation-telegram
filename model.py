from sqlalchemy import Column, String, Text, SmallInteger, ForeignKey, Integer
from sqlalchemy.ext.declarative import declarative_base


Base = declarative_base()


class Item(Base):
    __tablename__ = "item"
    id = Column(Integer, primary_key=True)
    label = Column(String(32), nullable=False)
    content = Column(Text, nullable=False)

    def __repr__(self):
        return f"<Item(label='{self.label}', content='{self.content}')>"


class Interaction(Base):
    __tablename__ = "interaction"
    user_id = Column(Integer, primary_key=True)
    item_id = Column(Integer, ForeignKey("item.id"), primary_key=True)
    relevance = Column(SmallInteger)
    quality = Column(SmallInteger)

    def __repr__(self):
        return f"<Interaction(user_id='{self.user_id}', item_id='{self.item_id}, 'relevance'={self.relevance}, " \
               f"'quality'={self.quality})> "
