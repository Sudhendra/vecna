class ToolPolicy:
    def __init__(self, policy_config) -> None:
        self._deny = set(policy_config.deny)
        self._ask = set(policy_config.ask)
        self._allow = set(policy_config.allow)

    def is_denied(self, name: str) -> bool:
        if name in self._deny:
            return True
        if self._allow and name not in self._allow:
            return True
        return False

    def is_ask(self, name: str) -> bool:
        return name in self._ask
