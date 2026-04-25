from arkham_card_maker.bleeding.engine import calculate_pixel_dimensions
from arkham_card_maker.render_options import ExportBleed, ExportSize


def test_calculate_pixel_dimensions_matches_old_formula():
    assert calculate_pixel_dimensions(300, ExportBleed.THREE_MM, ExportSize.POKER_SIZE) == (821, 1121)
