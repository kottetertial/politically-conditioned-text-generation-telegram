from functools import wraps
from typing import Callable

from config import ADMIN_ID


def admin_tool(func) -> Callable:
    @wraps(func)
    async def wrapped(update, context, *args, **kwargs) -> None:
        user_id = str(update.effective_user.id)
        if user_id == ADMIN_ID:
            return await func(update, context, *args, **kwargs)
    return wrapped
