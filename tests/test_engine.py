from arkham_card_maker import CardRenderer, RenderOptions
from arkham_card_maker.compat.workspace import RenderWorkspace


def test_renderer_does_not_call_legacy_double_render(monkeypatch):
    calls = []
    original = RenderWorkspace.generate_card_image

    def spy(self, json_data, layout_only=False, silence=False):
        calls.append({"layout_only": layout_only, "silence": silence})
        return original(self, json_data, layout_only=layout_only, silence=silence)

    monkeypatch.setattr(RenderWorkspace, "generate_card_image", spy)
    renderer = CardRenderer()
    renderer.render({"type": "事件卡", "class": "中立", "name": "测试", "body": "测试正文", "traits": []}, RenderOptions(bleed=0))

    assert calls == [{"layout_only": True, "silence": False}]
