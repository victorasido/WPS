from __future__ import annotations

import inspect
import logging
from collections.abc import Awaitable, Callable
from functools import wraps
from typing import Any, TypeVar, cast

from telegram import Update
from telegram.ext import ConversationHandler

from src.infra.database import LogRepository, session_manager

logger = logging.getLogger(__name__)
log_repo = LogRepository()

AsyncFunc = TypeVar("AsyncFunc", bound=Callable[..., Awaitable[Any]])


def handle_workflow_error(
    *,
    process_name: str,
    error_message_factory: Callable[[str], str],
    message_arg: str = "status_msg",
    message_method: str = "edit_text",
    clear_session: bool = False,
    return_value: Any = ConversationHandler.END,
) -> Callable[[AsyncFunc], AsyncFunc]:
    def decorator(func: AsyncFunc) -> AsyncFunc:
        signature = inspect.signature(func)

        @wraps(func)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            bound = signature.bind_partial(*args, **kwargs)
            update = _resolve_update(bound.arguments, args)
            message_target = bound.arguments.get(message_arg)
            user_id = getattr(getattr(update, "effective_user", None), "id", None)
            initial_session = session_manager.get_session(user_id) if user_id is not None else None
            doc_name = initial_session.get("doc_name") if initial_session else None

            try:
                return await func(*args, **kwargs)
            except Exception as error:
                logger.exception("%s failed", process_name)
                log_repo.log_error(doc_name, str(error))

                await _send_error_message(
                    update=update,
                    message_target=message_target,
                    method_name=message_method,
                    text=error_message_factory(str(error)),
                )

                if clear_session and user_id is not None:
                    session_manager.clear_session(user_id)

                return return_value

        return cast(AsyncFunc, wrapper)

    return decorator


def _resolve_update(arguments: dict[str, Any], args: tuple[Any, ...]) -> Update | None:
    update = arguments.get("update")
    if isinstance(update, Update):
        return update

    for arg in args:
        if isinstance(arg, Update):
            return arg
    return None


async def _send_error_message(
    *,
    update: Update | None,
    message_target: Any,
    method_name: str,
    text: str,
) -> None:
    try:
        if message_target is not None:
            method = getattr(message_target, method_name, None)
            if callable(method):
                await method(text, parse_mode="Markdown")
                return

        if update and update.message:
            await update.message.reply_text(text, parse_mode="Markdown")
    except Exception:
        pass
