from abc import ABC, abstractmethod
from models.incident import TriageRequest, TriageResponse

class IAiClient(ABC):
    @abstractmethod
    async def triage(self, request: TriageRequest) -> TriageResponse:
        """Call the AI Engine triage endpoint and return the response."""
        pass
