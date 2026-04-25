import pytest

click = pytest.importorskip("click")
from click.testing import CliRunner

from arkham_card_maker.cli.main import cli


def test_config_show_outputs_json():
    result = CliRunner().invoke(cli, ["config", "show"])

    assert result.exit_code == 0
    assert "dpi" in result.output
