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


def test_renderer_reuses_workspace_for_same_context(monkeypatch):
    created = 0
    original_init = RenderWorkspace.__init__

    def spy_init(self, *args, **kwargs):
        nonlocal created
        created += 1
        original_init(self, *args, **kwargs)

    monkeypatch.setattr(RenderWorkspace, "__init__", spy_init)
    renderer = CardRenderer()
    options = RenderOptions(bleed=0, working_dir=".")
    card = {"type": "事件卡", "class": "中立", "name": "测试", "body": "测试正文", "traits": []}

    renderer.render(card, options)
    renderer.render(card, options)

    assert created == 1
