from decimal import Decimal

from matching_agent.rules import gst_component, is_valid_abn


def test_gst_half_up_to_the_cent():
    assert gst_component(Decimal("10.05")) == Decimal("1.01")
    assert gst_component(Decimal("10.04")) == Decimal("1.00")
    assert gst_component(Decimal("250.00")) == Decimal("25.00")
    assert gst_component(Decimal("90.80")) == Decimal("9.08")
    assert gst_component(Decimal("220.00")) == Decimal("22.00")


def test_seed_abns_pass_checksum():
    valid = ["51824753556", "53000000770", "53000000851", "53000000883", "53000000900"]
    assert all(is_valid_abn(abn) for abn in valid)
    assert is_valid_abn("51 824 753 556")
    assert not is_valid_abn("12345678901")
    assert not is_valid_abn("123")
