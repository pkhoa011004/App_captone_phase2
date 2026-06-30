from abc import ABC, abstractmethod


class INotifier(ABC):
    """
    DIP: High-level modules phụ thuộc vào abstraction này,
         không phụ thuộc trực tiếp vào SlackNotifier hay bất kỳ impl cụ thể nào.

    ISP: Interface nhỏ gọn, chỉ expose phương thức notify() cần thiết.
         Client không bị ép implement những gì không dùng.

    OCP: Thêm kênh thông báo mới (PagerDuty, Teams...) chỉ cần tạo
         class mới implement INotifier — không sửa code hiện có.
    """

    @abstractmethod
    def notify(self, message: str) -> None:
        """Gửi một thông báo với nội dung message."""
        ...