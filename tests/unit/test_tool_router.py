from vecna.tools.router import ToolRouter


def test_router_ranks_tools():
    router = ToolRouter()
    router.record("search", success=True)
    router.record("search", success=True)
    router.record("exec", success=False)
    ranked = router.rank(["exec", "search"])
    assert ranked[0] == "search"
