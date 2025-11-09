import sys

from models.config import AppConfig


def test_cli_skip_empty_does_not_save(tmp_path, monkeypatch):
    # Prepare dummy ConfigManager for CLI to control output dir and logging
    class DummyCfgMgr:
        def get_config(self):
            cfg = AppConfig(
                output_format="json",
                output_directory=str(tmp_path),
                enable_deduplication=True,
            )
            # Also set logging file into tmp_path to avoid touching project logs
            cfg.logging.file = str(tmp_path / "cli_skip_empty.log")
            return cfg

    # Dummy controller that returns no messages and should not be asked to save in skip-empty mode
    class DummyController:
        def run_once(self):
            return []

        def run_and_save(self, **kwargs):
            raise AssertionError("run_and_save should not be called when --skip-empty and no messages")

    import cli.run_extraction as cli_mod
    monkeypatch.setattr(cli_mod, "ConfigManager", DummyCfgMgr)
    monkeypatch.setattr(cli_mod, "MainController", DummyController)

    # Simulate CLI args
    monkeypatch.setattr(sys, "argv", [
        "prog", "--skip-empty", "--no-progress", "--prefix", "cli_skip", "--format", "json", "--outdir", str(tmp_path)
    ])

    # Execute main
    cli_mod.main()

    # Verify no output files created
    assert not list(tmp_path.glob("cli_skip_*.json"))


def test_cli_without_skip_empty_still_not_save_when_empty(tmp_path, monkeypatch):
    # Use real MainController.run_and_save but control output path via ConfigManager
    class DummyCfgMgr:
        def get_config(self):
            cfg = AppConfig(
                output_format="txt",
                output_directory=str(tmp_path),
                enable_deduplication=True,
            )
            cfg.logging.file = str(tmp_path / "cli_no_skip_empty.log")
            return cfg

    import cli.run_extraction as cli_mod

    # Patch CLI ConfigManager
    monkeypatch.setattr(cli_mod, "ConfigManager", DummyCfgMgr)

    # Ensure the controller returns empty messages before save
    from controllers import main_controller as mc_mod

    class EmptyController(mc_mod.MainController):
        def run_once(self):
            return []

    # Patch the class used by CLI to our EmptyController
    monkeypatch.setattr(cli_mod, "MainController", EmptyController)

    # Also patch ConfigManager inside real MainController to use our DummyCfgMgr for saving path
    monkeypatch.setattr(mc_mod, "ConfigManager", DummyCfgMgr)

    # Simulate CLI args (no --skip-empty)
    monkeypatch.setattr(sys, "argv", [
        "prog", "--no-progress", "--prefix", "cli_noskip", "--format", "txt", "--outdir", str(tmp_path)
    ])

    # Execute main
    cli_mod.main()

    # Verify no output files created since message list is empty
    assert not list(tmp_path.glob("cli_noskip_*.txt"))