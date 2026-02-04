from click.testing import CliRunner

from vecna.cli.main import cli


def test_tools_pending_empty():
    runner = CliRunner()
    result = runner.invoke(cli, ["tools", "pending"])
    assert result.exit_code == 0
