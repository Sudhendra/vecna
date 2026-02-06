class CuriosityEngine:
    def from_contradictions(self, contradictions):
        goals = []
        for item in contradictions:
            goals.append({"goal": f"explore contradiction: {item['content']}"})
        return goals
