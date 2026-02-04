from dataclasses import dataclass
from typing import Dict, List


@dataclass
class ApprovalRequest:
    request_id: str
    tool_name: str
    status: str


class ApprovalStore:
    def __init__(self) -> None:
        self._requests: Dict[str, ApprovalRequest] = {}

    def add_request(self, request: ApprovalRequest) -> None:
        self._requests[request.request_id] = request

    def get_request(self, request_id: str) -> ApprovalRequest | None:
        return self._requests.get(request_id)

    def get_pending(self) -> List[ApprovalRequest]:
        return [req for req in self._requests.values() if req.status == "pending"]

    def update_status(self, request_id: str, status: str) -> None:
        if request_id in self._requests:
            self._requests[request_id].status = status
