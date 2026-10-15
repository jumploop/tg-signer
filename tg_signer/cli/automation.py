import asyncio
import logging
from functools import partial

import click
from click import Group

from tg_signer.automation import UserAutomation

from .signer import (
    dialogs_option,
    export_config,
    export_file_option,
    from_folder_option,
    import_config,
    import_file_option,
    make_worker,
    run_coroutines,
    tg_signer,
)

get_automation = partial(make_worker, UserAutomation)


@tg_signer.group(name="automation", help="配置和运行自动化")
@click.pass_context
def tg_automation(ctx: click.Context):
    logger = logging.getLogger("tg-signer")
    if ctx.invoked_subcommand in ["run"]:
        if proxy := ctx.obj.get("proxy"):
            logger.info(
                "Using proxy: %s"
                % f"{proxy['scheme']}://{proxy['hostname']}:{proxy['port']}"
            )
        logger.info(f"Using account: {ctx.obj['account']}")


tg_automation: Group


@tg_automation.command(name="list", help="列出已有配置")
@click.pass_obj
def list_(obj):
    # 只枚举已有任务目录:构造 worker 会带上默认任务名(my_task)并据此建目录,
    # 把「列出」变成「创建」。
    for task_name in UserAutomation.list_task_names(obj["workdir"]):
        click.echo(task_name)


@tg_automation.command(help="根据配置运行自动化(可指定多个任务共享同一 Client)")
@click.argument("task_names", nargs=-1)
@dialogs_option(default=20)
@from_folder_option
@click.pass_obj
def run(obj, task_names, num_of_dialogs, folder):
    if not task_names:
        raise click.UsageError("At least one task name is required")
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    coros = [
        get_automation(name, obj, loop=loop).run(num_of_dialogs, folder=folder)
        for name in task_names
    ]
    run_coroutines(loop, coros)


@tg_automation.command(help="初始化或重置配置")
@click.argument("task_name", nargs=1, default="my_automation")
@click.pass_obj
def init(obj, task_name):
    automation = get_automation(task_name, obj)
    config = automation.template_config()
    automation.write_config(config)
    click.echo(f"已生成模板配置: {automation.config_file}")


@tg_automation.command(help="重新配置（使用模板覆盖）")
@click.argument("task_name", nargs=1, default="my_automation")
@click.pass_obj
def reconfig(obj, task_name):
    automation = get_automation(task_name, obj)
    return automation.reconfig()


@tg_automation.command(help="校验配置")
@click.argument("task_name", nargs=1, default="my_automation")
@click.pass_obj
def validate(obj, task_name):
    automation = get_automation(task_name, obj)
    # 配置文件不存在时 load_config() 会走 reconfig() → 写模板,把「校验」变成
    # 「创建」。这里用不创建目录的查询:校验不存在的任务时,磁盘上不留任何痕迹
    # (用 _resolve_config_file()/task_dir 会创建空任务目录)。
    config_path = automation.find_existing_config_file()
    if config_path is None:
        default_path = automation.config_dir_path() / "config.json"
        raise click.ClickException(
            f"配置不存在: {default_path}（可用 `automation init {task_name}` 生成模板配置）"
        )
    try:
        automation.load_config()
    except Exception as exc:  # noqa: BLE001
        raise click.ClickException(str(exc))
    click.echo("配置校验通过")


@tg_automation.command(
    help="""导出配置，默认为输出到终端。\n\n e.g.\n\n  tg-signer automation export -O config.json mytask\n\n  tg-signer automation export mytask > config.json"""
)
@click.argument("task_name")
@export_file_option
@click.pass_obj
def export(obj, task_name: str, file: str = None):
    automation = get_automation(task_name, obj)
    export_config(automation, file)


@tg_automation.command(
    name="import",
    help="""导入配置，默认为从终端读取。\n\n e.g.\n\n  tg-signer automation import -I config.json mytask\n\n  cat config.json | tg-signer automation import mytask""",
)
@click.argument("task_name")
@import_file_option
@click.pass_obj
def import_(obj, task_name: str, file: str = None):
    automation = get_automation(task_name, obj)
    import_config(automation, file)
