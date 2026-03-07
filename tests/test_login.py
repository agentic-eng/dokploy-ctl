from click.testing import CliRunner

from dokployctl.cli import cli


def test_login_creates_config(tmp_path, monkeypatch):
    monkeypatch.setattr("dokployctl.cli.DEFAULT_CONFIG_DIR", tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["login", "--url", "https://dokploy.example.com", "--token", "my-token-123"])
    assert result.exit_code == 0
    assert (tmp_path / "token").read_text().strip() == "my-token-123"
    assert (tmp_path / "url").read_text().strip() == "https://dokploy.example.com"


def test_login_overwrites_existing(tmp_path, monkeypatch):
    monkeypatch.setattr("dokployctl.cli.DEFAULT_CONFIG_DIR", tmp_path)
    (tmp_path / "token").write_text("old-token")
    (tmp_path / "url").write_text("https://old.example.com")
    runner = CliRunner()
    result = runner.invoke(cli, ["login", "--url", "https://new.example.com", "--token", "new-token"])
    assert result.exit_code == 0
    assert (tmp_path / "token").read_text().strip() == "new-token"


def test_login_missing_args(tmp_path, monkeypatch):
    monkeypatch.setattr("dokployctl.cli.DEFAULT_CONFIG_DIR", tmp_path)
    runner = CliRunner()
    result = runner.invoke(cli, ["login", "--url", "https://example.com"])
    assert result.exit_code != 0
