class ToolPolicy:
    def __init__(self, policy_config) -> None:
        self._deny = set(policy_config.deny)
        self._ask = set(policy_config.ask)

    def is_denied(self, name: str) -> bool:
        return name in self._deny

    def is_ask(self, name: str) -> bool:
        return name in self._ask
