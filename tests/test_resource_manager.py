from pathlib import Path

from arkham_card_maker.resource_manager import FontManager, ImageManager


def test_font_manager_loads_language_config():
    manager = FontManager(font_folder=str(Path(__file__).parents[1] / "fonts"), lang="zh")
    assert manager.get_current_config() is not None
    assert manager.get_lang_font("正文字体").name


def test_image_manager_loads_templates():
    manager = ImageManager(image_folder=str(Path(__file__).parents[1] / "images"))
    assert manager.get_image("支援卡-守护者") is not None
