"""Unit tests for the security-sensitive pure-Python pieces (no Windows needed to run these)."""
import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import calc, layout, textsafe
from core.index import is_safe_launch_target
from core.settings import sanitize
from core.system import is_allowed_uri
from core.winkey import VK_LWIN, WinKeyLogic
from PyQt6.QtCore import QRect


# ---------------------------------------------------------------- textsafe
def test_textsafe_strips_control_and_bidi_chars():
    assert textsafe.clean_label("evil\u202enretaht") == "evilnretaht"
    assert textsafe.clean_label("a\u200bb\u200cc") == "abc"
    assert textsafe.clean_label("normal name") == "normal name"


def test_textsafe_truncates():
    out = textsafe.clean_label("x" * 500, maxlen=10)
    assert len(out) == 10 and out.endswith("\u2026")


def test_textsafe_non_string_is_empty():
    assert textsafe.clean_label(12345) == ""
    assert textsafe.clean_label(None) == ""


# ---------------------------------------------------------------- calculator (no eval, bounded)
def test_calc_basic_and_functions():
    assert calc.evaluate("2+2") == "4"
    assert calc.evaluate("sqrt(9)") == "3"


def test_calc_rejects_non_math_text():
    assert calc.evaluate("open the pod bay doors") is None
    assert calc.evaluate("__import__('os')") is None
    assert calc.evaluate("") is None


def test_calc_rejects_dunder_and_attribute_access():
    for expr in ("().__class__", "[].__class__.__base__", "os.system('x')", "1.__add__(2)"):
        assert calc.evaluate(expr) is None


def test_calc_bounds_huge_expressions():
    assert calc.evaluate("9" * 300) is None                # too long
    assert calc.evaluate("2**99999999999999") is None       # blocked before it eats CPU/RAM
    assert calc.evaluate("(" * 60 + "1" + ")" * 60) is None  # too many parens


def test_calc_never_raises_on_garbage():
    for expr in ["1/0", "1%0", "2**2**2**2**2**2**2**2**2", "nan", "inf"]:
        calc.evaluate(expr)  # must not raise


# ---------------------------------------------------------------- settings sanitizer
def test_settings_drops_unknown_keys():
    assert sanitize({"totally_made_up": 1}) == {}


def test_settings_rejects_bad_types_and_ranges():
    out = sanitize({"dock_icon_size": "99", "dock_mode": "smart", "clock_24h": "yes"})
    assert out == {"dock_mode": "smart"}


def test_settings_rejects_oversized_or_malformed_collections():
    huge_pins = [{"name": "a", "exe": "x"}] * 200
    out = sanitize({"dock_pins": huge_pins})
    assert "dock_pins" not in out
    out2 = sanitize({"weather_place": {"name": "x", "lat": 999, "lon": 0}})
    assert "weather_place" not in out2
    out3 = sanitize({"notes_text": "y" * 500_000})
    assert "notes_text" not in out3


def test_settings_not_a_dict_is_empty():
    assert sanitize(["a", "b"]) == {}
    assert sanitize("hello") == {}
    assert sanitize(None) == {}


def test_settings_accepts_good_values():
    out = sanitize({"dock_mode": "always", "dock_icon_size": 48, "week_start": 6})
    assert out == {"dock_mode": "always", "dock_icon_size": 48, "week_start": 6}


# ---------------------------------------------------------------- launch / URI allow-lists
def test_launch_target_blocks_device_and_missing_paths():
    assert not is_safe_launch_target("\\\\.\\PhysicalDrive0")
    assert not is_safe_launch_target("/definitely/not/a/real/path/xyz")
    assert not is_safe_launch_target("")
    assert not is_safe_launch_target("a" * 5000)


def test_launch_target_allows_store_apps_and_real_files(tmp_path):
    assert is_safe_launch_target("shell:AppsFolder\\Microsoft.WindowsCalculator_8wekyb3d8bbwe!App")
    f = tmp_path / "app.exe"
    f.write_text("x")
    assert is_safe_launch_target(str(f))


def test_uri_allow_list():
    assert is_allowed_uri("https://example.com")
    assert is_allowed_uri("ms-settings:bluetooth")
    assert not is_allowed_uri("file:///etc/passwd")
    assert not is_allowed_uri("javascript:alert(1)")
    assert not is_allowed_uri("search-ms:query=x")
    assert not is_allowed_uri("a" * 3000)
    assert not is_allowed_uri("https://x.com\nmalicious")


# ---------------------------------------------------------------- layout (no overlap)
def test_layout_collides_and_free_spot():
    a = QRect(0, 0, 100, 100)
    b = QRect(50, 50, 100, 100)
    assert layout.collides(a, [b])
    area = QRect(0, 0, 1000, 1000)
    spot = layout.find_free_spot(100, 100, area, [a, b])
    assert spot is not None
    assert not layout.collides(QRect(spot, a.size()), [a, b])


def test_layout_clamp_into_bounds():
    r = QRect(-50, -50, 100, 100)
    area = QRect(0, 0, 800, 600)
    clamped = layout.clamp_into(r, area)
    assert area.contains(clamped)


def test_layout_no_free_spot_when_area_too_small():
    area = QRect(0, 0, 50, 50)
    assert layout.find_free_spot(100, 100, area, []) is None


# ---------------------------------------------------------------- Windows-key hook logic (pure state machine)
def test_winkey_solo_tap_triggers():
    logic = WinKeyLogic()
    logic.feed(VK_LWIN, True, False)
    swallow, action = logic.feed(VK_LWIN, False, False)
    assert action == "win_solo" and not swallow


def test_winkey_combo_does_not_trigger():
    logic = WinKeyLogic()
    logic.feed(VK_LWIN, True, False)
    logic.feed(0x44, True, False)   # 'D'
    logic.feed(0x44, False, False)
    _swallow, action = logic.feed(VK_LWIN, False, False)
    assert action is None


def test_winkey_ctrl_esc_triggers_and_task_manager_does_not():
    logic = WinKeyLogic()
    logic.feed(0xA2, True, False)   # ctrl
    swallow, action = logic.feed(0x1B, True, False)  # esc
    assert swallow and action == "ctrl_esc"

    logic2 = WinKeyLogic()
    logic2.feed(0xA2, True, False)   # ctrl
    logic2.feed(0xA0, True, False)   # shift
    _swallow, action2 = logic2.feed(0x1B, True, False)
    assert action2 is None                              # Ctrl+Shift+Esc stays Task Manager


def test_winkey_ignores_injected_events():
    logic = WinKeyLogic()
    logic.feed(VK_LWIN, True, True)
    _swallow, action = logic.feed(VK_LWIN, False, True)
    assert action is None
