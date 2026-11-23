from dualcontrol.models import LightingSettings
from dualcontrol.services.lighting_engine import compute_effect_rgb


def test_static_color_scales_by_lightbar_brightness():
    cfg = LightingSettings(red=100, green=200, blue=50, effect_mode="static", lightbar_brightness=50)
    assert compute_effect_rgb(cfg, elapsed_s=0.0) == (50, 100, 25)


def test_breathing_oscillates_between_zero_and_target():
    cfg = LightingSettings(red=0, green=120, blue=200, effect_mode="breathing", effect_speed=50, lightbar_brightness=100)
    start = compute_effect_rgb(cfg, elapsed_s=0.0)
    assert start == (0, 0, 0)
    # Mitad de periodo: brillo máximo
    freq = 0.10 + (50 / 100.0) * 1.90
    peak = compute_effect_rgb(cfg, elapsed_s=0.5 / freq)
    assert peak == (0, 120, 200)


def test_battery_mode_colors_and_low_battery_flash():
    cfg = LightingSettings(effect_mode="battery", lightbar_brightness=100, battery_low_flashing=True)
    high = compute_effect_rgb(cfg, elapsed_s=0.0, battery_level=90)
    assert high[1] > high[0]  # Verde dominante

    low_on = compute_effect_rgb(cfg, elapsed_s=0.0, battery_level=15)
    low_off = compute_effect_rgb(cfg, elapsed_s=0.4, battery_level=15)
    assert low_on[0] == 255
    assert low_off == (0, 0, 0)
