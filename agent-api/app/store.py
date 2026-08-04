from app.models import TicketResponse


class InMemoryTicketStore:
    def __init__(self) -> None:
        self._tickets: dict[str, TicketResponse] = {}

    def save(self, ticket: TicketResponse) -> None:
        self._tickets[ticket.id] = ticket

    def get(self, ticket_id: str) -> TicketResponse | None:
        return self._tickets.get(ticket_id)

    def list(self) -> list[TicketResponse]:
        return sorted(self._tickets.values(), key=lambda item: item.created_at, reverse=True)

    def clear(self) -> None:
        self._tickets.clear()


store = InMemoryTicketStore()
