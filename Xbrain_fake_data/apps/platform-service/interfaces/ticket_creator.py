from abc import ABC, abstractmethod


class ITicketCreator(ABC):
    """
    DIP: IncidentService phụ thuộc vào abstraction này,
         không phụ thuộc trực tiếp vào JiraTicketCreator.

    ISP: Interface tách biệt hoàn toàn với INotifier.
         Nếu sau này cần tạo ticket GitHub Issues, chỉ implement interface này.

    OCP: Thêm hệ thống ticket mới (Linear, GitHub...) không cần sửa IncidentService.
    """

    @abstractmethod
    def create_ticket(self, summary: str, description: str) -> str:
        """
        Tạo một ticket mới và trả về ticket ID.
        """
        ...