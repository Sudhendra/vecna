from click.testing import CliRunner

from vecna.cli.main import cli


def test_memory_dream_command():
    runner = CliRunner()
    result = runner.invoke(cli, ["memory", "dream", "--dry-run"])
    assert result.exit_code == 0
