import json
import tomllib
from pathlib import Path

import click

from ..engine import CardRenderer
from ..render_options import RenderOptions
from ..worker import BatchRenderer

DEFAULT_CONFIG = """[render]\ndpi = 300\nformat = "PNG"\nquality = 95\nbleed = 0\nbleed_mode = "裁剪"\nbleed_model = "镜像出血"\n\n[render.image]\nsaturation = 1.0\nbrightness = 1.0\ngamma = 1.0\n\n[lama]\nbase_url = "http://localhost:8080"\n"""


def _load_config(path):
    if not path:
        return {}
    with open(path, "rb") as file:
        return tomllib.load(file)


def _build_options(config_path=None, **overrides):
    config = _load_config(config_path)
    render = dict(config.get("render", {}))
    image = render.pop("image", {}) if isinstance(render.get("image", {}), dict) else {}
    lama = config.get("lama", {})
    values = {
        "dpi": render.get("dpi", 300),
        "format": render.get("format", "PNG"),
        "quality": render.get("quality", 95),
        "bleed": render.get("bleed", 0),
        "bleed_mode": render.get("bleed_mode", "裁剪"),
        "bleed_model": render.get("bleed_model", "镜像出血"),
        "saturation": image.get("saturation", 1.0),
        "brightness": image.get("brightness", 1.0),
        "gamma": image.get("gamma", 1.0),
        "lama_base_url": lama.get("base_url", "http://localhost:8080"),
    }
    for key, value in overrides.items():
        if value is not None:
            values[key] = value
    return RenderOptions(**values)


@click.group()
def cli():
    """阿卡姆卡牌渲染 CLI。"""


@cli.command()
@click.argument("card", type=click.Path(exists=True))
@click.option("-o", "--output", type=click.Path(), help="输出文件路径")
@click.option("--dpi", type=int, help="DPI")
@click.option("--bleed", type=int, help="出血 mm")
@click.option("--format", "output_format", type=click.Choice(["PNG", "JPG"]), help="输出格式")
@click.option("--quality", type=int, help="JPG 质量")
@click.option("-c", "--config", "config_path", type=click.Path(exists=True), help="配置文件")
def render(card, output, dpi, bleed, output_format, quality, config_path):
    """渲染单张 .card 文件。"""
    try:
        options = _build_options(config_path, dpi=dpi, bleed=bleed, format=output_format, quality=quality)
        result = CardRenderer().render(card, options)
        output_path = output or str(Path(card).with_suffix(".png"))
        saved = result.save(output_path) if result.back is None else result.save_all(Path(output_path).with_suffix(""))
        click.echo(f"渲染完成：{saved}")
    except Exception as exc:
        raise click.ClickException(f"渲染失败：{exc}") from exc


@cli.command()
@click.argument("pattern")
@click.option("-w", "--workers", type=int, default=1, help="并发进程数")
@click.option("-r", "--recursive", is_flag=True, help="递归搜索子目录")
@click.option("-o", "--output-dir", type=click.Path(), default="export", help="输出目录")
@click.option("-c", "--config", "config_path", type=click.Path(exists=True), help="配置文件")
def batch(pattern, workers, recursive, output_dir, config_path):
    """批量渲染 .card 文件。"""
    try:
        source = Path(pattern)
        if source.is_dir():
            cards = sorted(source.rglob("*.card") if recursive else source.glob("*.card"))
        else:
            cards = sorted(Path().glob(pattern))
        if not cards:
            raise click.ClickException("未找到 card 文件。")
        options = _build_options(config_path)
        renderer = BatchRenderer()
        results = renderer.render(cards, output_dir, options, workers=workers)
        for item in results:
            click.echo(f"完成：{item['card']} -> {', '.join(item['saved_files'])}")
    except click.ClickException:
        raise
    except Exception as exc:
        raise click.ClickException(f"批量渲染失败：{exc}") from exc


@cli.group()
def config():
    """配置管理。"""


@config.command("init")
@click.option("-f", "--force", is_flag=True, help="覆盖已有配置")
def config_init(force):
    path = Path("arkham-card-maker.toml")
    if path.exists() and not force:
        raise click.ClickException("配置文件已存在，如需覆盖请使用 --force。")
    path.write_text(DEFAULT_CONFIG, encoding="utf-8")
    click.echo(f"已生成配置文件：{path}")


@config.command("show")
@click.option("--toml", "as_toml", is_flag=True, help="TOML 格式输出")
def config_show(as_toml):
    if as_toml:
        click.echo(DEFAULT_CONFIG.rstrip())
    else:
        options = _build_options()
        click.echo(json.dumps(options.__dict__, ensure_ascii=False, indent=2))
