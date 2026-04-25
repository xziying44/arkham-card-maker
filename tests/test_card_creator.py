from arkham_card_maker.card_creator import CardCreator
from arkham_card_maker.resource_manager import FontManager, ImageManager


def test_create_card_bottom_map_restores_silence():
    font_manager = FontManager(lang="zh")
    image_manager = ImageManager()
    creator = CardCreator(font_manager, image_manager)
    data = {"type": "事件卡", "class": "中立", "name": "测试", "body": "测试正文", "traits": []}

    card = creator.create_card_bottom_map(data)

    assert card is not None
    assert font_manager.silence is False


def test_layout_only_keeps_text_metadata():
    font_manager = FontManager(lang="zh")
    image_manager = ImageManager()
    creator = CardCreator(font_manager, image_manager)
    data = {"type": "事件卡", "class": "中立", "name": "测试", "body": "测试正文", "traits": []}

    card = creator.create_card(data, layout_only=True)
    metadata = card.get_text_layer_metadata()

    assert metadata
    assert any(item.get("text") for item in metadata if item.get("type") != "image")
