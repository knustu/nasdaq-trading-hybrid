from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_windows_launchers_use_their_own_directory():
    for name in (
        "install_windows.bat",
        "build_cpp.bat",
        "run_app.bat",
        "run_cli.bat",
        "run_tests.bat",
        "START_HERE.bat",
        "diagnose_windows.bat",
    ):
        text = (ROOT / name).read_text(encoding="ascii")
        assert 'cd /d "%~dp0"' in text


def test_install_script_keeps_error_window_open():
    text = (ROOT / "install_windows.bat").read_text(encoding="ascii")
    assert "pause" in text
    assert "install_result.txt" in text


def test_env_editor_replaces_duplicate_key(tmp_path):
    from tools.set_env_value import set_value

    env = tmp_path / ".env"
    env.write_text("A=1\nREQUIRE_CPP_ENGINE=true\nREQUIRE_CPP_ENGINE=true\n", encoding="utf-8")
    set_value(env, "REQUIRE_CPP_ENGINE", "false")
    text = env.read_text(encoding="utf-8")
    assert text.count("REQUIRE_CPP_ENGINE=") == 1
    assert "REQUIRE_CPP_ENGINE=false" in text
