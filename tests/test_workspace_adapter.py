from arkham_card_maker.compat.workspace import RenderWorkspace


def test_workspace_reads_card_file(tmp_path):
    card = tmp_path / "a.card"
    card.write_text('{"type":"事件卡","name":"测试"}', encoding="utf-8")
    workspace = RenderWorkspace(workspace_path=tmp_path)

    assert workspace.get_file_content("a.card") == '{"type":"事件卡","name":"测试"}'
