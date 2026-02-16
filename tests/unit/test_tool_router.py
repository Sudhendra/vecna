from vecna.tools.router import ToolRouter
from vecna.tools.types import ToolSpec


def test_router_ranks_tools():
    router = ToolRouter()
    router.record("search", success=True)
    router.record("search", success=True)
    router.record("exec", success=False)
    ranked = router.rank(["exec", "search"])
    assert ranked[0] == "search"


def test_router_ranks_tools_by_tag_overlap():
    router = ToolRouter()
    router.record("http_request", success=True)
    router.record("http_request", success=True)
    router.record("web_search", success=True)
    router.record("web_search", success=False)

    specs = [
        ToolSpec(
            name="http_request",
            description="Fetch an HTTP or HTTPS URL",
            input_schema={"url": "string"},
            tags=["web", "http", "fetch"],
        ),
        ToolSpec(
            name="web_search",
            description="Search the web",
            input_schema={"query": "string"},
            tags=["web", "search"],
        ),
        ToolSpec(
            name="fs_read",
            description="Read a file",
            input_schema={"path": "string"},
            tags=["filesystem", "read"],
        ),
    ]

    ranked_specs = router.rank_specs_for_query(specs, "fetch web page over http")

    assert [spec.name for spec in ranked_specs] == ["http_request", "web_search", "fs_read"]
