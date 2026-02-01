from contextvars import ContextVar

REQUEST_ID_HEADER = "X-Request-ID"

_request_id_ctx: ContextVar[str] = ContextVar("request_id", default="-")


def set_request_id(value: str) -> None:
    _request_id_ctx.set(value)


def get_request_id() -> str:
    return _request_id_ctx.get()


def get_request_id_header() -> dict[str, str]:
    request_id = get_request_id()
    if not request_id or request_id == "-":
        return {}
    return {REQUEST_ID_HEADER: request_id}
