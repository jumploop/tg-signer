import json
import logging
import os
import re
import secrets
import shutil
import sqlite3
import threading
from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Iterable, List, Literal, Optional, Tuple

from tg_signer.config import AutomationConfig, BaseJSONConfig, SignConfigV3
from tg_signer.sign_record_store import SignRecordStore
from tg_signer.utils import resolve_log_under, resolve_under

logger = logging.getLogger("tg-signer")

ConfigKind = Literal["signer"]
NameGenKind = Literal["signer", "automation"]


@dataclass(frozen=True)
class ConfigKindMeta:
    """一种配置类型的元数据。

    这些信息原先散在两处：`CONFIG_META` 管「目录名 + 配置类」，`NAME_PREFIXES`
    管「随机名前缀」，而 `automation` 只出现在后者（它不按 signs/ 布局存储）。
    新增一种配置类型必须记得同时改两张表，漏一张就是运行期 KeyError。收敛成一张
    表后，缺哪个字段一眼可见。
    """

    cfg_cls: type[BaseJSONConfig]
    name_prefix: str
    dir_name: Optional[str] = None  # None 表示不走 <workdir>/<dir>/<name>/ 布局


CONFIG_KINDS: dict[NameGenKind, ConfigKindMeta] = {
    "signer": ConfigKindMeta(SignConfigV3, "sign", "signs"),
    "automation": ConfigKindMeta(AutomationConfig, "auto"),
}

DEFAULT_WORKDIR = Path(os.environ.get("TG_SIGNER_WORKDIR", ".signer"))
# 允许 WebUI 切换工作目录的根白名单(多个根用 os.pathsep 分隔)。未设置时
# 只允许初始工作目录的父目录 —— 否则 POST /api/state 既是一个任意目录创建
# 原语,也会让「插件加载」指向非预期的 <workdir>/handlers/*.py。
WORKDIR_ROOTS_ENV = "TG_SIGNER_WEBUI_WORKDIR_ROOTS"
LOG_DIR = Path("logs")
DEFAULT_LOG_FILE = LOG_DIR / "tg-signer.log"
# 与 tg_signer.webui.runner.DEFAULT_LOG_FILE_NAME 保持一致,统一主日志文件名
LOG_FILE_NAME = DEFAULT_LOG_FILE.name


@dataclass
class ConfigEntry:
    name: str
    path: Path
    updated_from_old: bool
    payload: Dict[str, Any]
    cfg: BaseJSONConfig


@dataclass
class UserInfo:
    user_id: str
    data: Dict[str, Any]
    path: Path
    latest_chats: List[Dict[str, Any]] = None


@dataclass
class SignRecord:
    task: str
    user_id: Optional[str]
    records: List[Tuple[str, str]]
    path: Path


def get_workdir(workdir: Optional[Path | str] = None, *, create: bool = True) -> Path:
    base = Path(workdir) if workdir else DEFAULT_WORKDIR
    if create:
        base.mkdir(parents=True, exist_ok=True)
    # 必须返回绝对路径。DEFAULT_WORKDIR 默认是相对的 ``.signer``，若原样返回，
    # UIState.log_path 就是 ``.signer/logs/tg-signer.log``：日志接口把它当作
    # 「相对 logs/ 根目录」再次拼接，resolve_log_under() 必然判定越界，/api/logs
    # 与 /api/logs/files 往返一次就全部 400 —— 表现为「日志文件有内容但页面空白」。
    return base.resolve()


def uses_dir_layout(kind: str) -> bool:
    """该 kind 是否走 ``<workdir>/<dir_name>/<name>/config.json`` 布局。

    `automation` 也在 `CONFIG_KINDS` 里，但不走这个布局，所以「不支持的配置类型」
    守卫不能只做成员判断，否则会把 automation 放行到一个并不存在的目录上。
    """
    meta = CONFIG_KINDS.get(kind)
    return meta is not None and meta.dir_name is not None


def _config_root(kind: ConfigKind, workdir: Optional[Path | str]) -> Path:
    meta = CONFIG_KINDS[kind]
    if meta.dir_name is None:  # automation 走 automations/ 之外的自有布局
        raise ValueError(f"{kind} 不按目录布局存储配置")
    return get_workdir(workdir) / meta.dir_name


def _config_path(kind: ConfigKind, name: str, workdir: Optional[Path | str]) -> Path:
    """`<root>/<name>/config.json`;`name` 越界时抛 `ValueError`。

    读写删三个动作都走这里,所以路径校验只需要在这一层做一次。
    """
    return resolve_under(_config_root(kind, workdir), name) / "config.json"


def list_task_names(
    kind: ConfigKind, workdir: Optional[Path | str] = None
) -> List[str]:
    root = _config_root(kind, workdir)
    if not root.is_dir():
        return []
    # 只列出真正存在 config.json 的配置;已删除配置残留的目录不算配置。
    return sorted(
        p.name for p in root.iterdir() if p.is_dir() and (p / "config.json").is_file()
    )


def list_automation_names(workdir: Optional[Path | str] = None) -> List[str]:
    """List automation task names from <workdir>/automations/*/.

    Automation 配置支持 config.json / config.yaml / config.yml 三种文件名,
    与 CLI 的解析顺序一致,只要存在其一即视为有效任务。
    """
    base = get_workdir(workdir)
    root = base / "automations"
    if not root.is_dir():
        return []
    return sorted(
        p.name
        for p in root.iterdir()
        if p.is_dir()
        and any(
            (p / name).is_file()
            for name in ("config.json", "config.yaml", "config.yml")
        )
    )


def resolve_automation_config_file(
    name: str, workdir: Optional[Path | str] = None
) -> Optional[Path]:
    """返回 automations/<name>/ 下第一个存在的配置文件。"""
    root = resolve_under(get_workdir(workdir) / "automations", name)
    for file_name in ("config.json", "config.yaml", "config.yml"):
        candidate = root / file_name
        if candidate.is_file():
            return candidate
    return None


def _read_automation_payload(path: Path) -> Dict[str, Any]:
    if path.suffix in {".yml", ".yaml"}:
        try:
            import yaml  # type: ignore
        except ModuleNotFoundError as exc:
            raise ValueError("未安装 pyyaml，无法读取 YAML 配置") from exc
        try:
            with open(path, "r", encoding="utf-8") as fp:
                payload = yaml.safe_load(fp) or {}
        except yaml.YAMLError as exc:
            # yaml.YAMLError 不是 ValueError 子类（已核实），原样冒泡会让
            # server 的 400 兜底失效，把一份手改坏的 YAML 变成 500。
            raise ValueError(f"YAML 解析失败: {exc}") from exc
        if not isinstance(payload, dict):
            raise ValueError("YAML 配置必须是字典结构")
        return payload
    with open(path, "r", encoding="utf-8") as fp:
        return json.load(fp)


def load_automation_config(
    name: str, workdir: Optional[Path | str] = None
) -> ConfigEntry:
    config_file = resolve_automation_config_file(name, workdir)
    if config_file is None:
        raise FileNotFoundError(
            f"配置不存在: {get_workdir(workdir) / 'automations' / name}"
        )
    payload = _read_automation_payload(config_file)
    cfg, from_old, err = AutomationConfig.load_checked(payload)
    if cfg is None:
        raise ValueError(f"无法解析配置: {config_file}（{err or '未知原因'}）")
    return ConfigEntry(
        name=name,
        path=config_file,
        updated_from_old=from_old,
        payload=cfg.to_jsonable(),
        cfg=cfg,
    )


def save_automation_config(
    name: str,
    content: Dict[str, Any] | str | BaseJSONConfig,
    workdir: Optional[Path | str] = None,
) -> Path:
    """校验并写入 automations/<name>/config.json（JSON 优先于 YAML）。"""
    if isinstance(content, BaseJSONConfig):
        cfg = content
    else:
        data = json.loads(content) if isinstance(content, str) else content
        cfg, _from_old, err = AutomationConfig.load_checked(data)
        if cfg is None:
            raise ValueError(err or "配置校验失败")
    config_dir = resolve_under(get_workdir(workdir) / "automations", name)
    config_file = config_dir / "config.json"
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as fp:
        json.dump(cfg.to_jsonable(), fp, ensure_ascii=False, indent=2)
    return config_file


def delete_automation_config(name: str, workdir: Optional[Path | str] = None) -> Path:
    # resolve_automation_config_file 内部已做路径校验,非法名称在这里就会抛错,
    # 不会走到下面的 rmtree。
    config_file = resolve_automation_config_file(name, workdir)
    if config_file is None:
        raise FileNotFoundError(
            f"配置不存在: {get_workdir(workdir) / 'automations' / name}"
        )
    shutil.rmtree(config_file.parent, ignore_errors=True)
    return config_file


def resolve_chat_id_for_selector(
    requested: "int | str | None",
    chats_by_id: Dict[str, Dict[str, Any]],
) -> Optional[str]:
    """把任意形式的 chat_id(int / str / "@username" / "username")解析成
    chats_by_id 中存在的 key(str 化的 chat.id)。

    匹配规则:
    1. ``int`` → 直接 str(value) 命中 chat.id;
    2. ``str`` 去掉前导 ``@``,先按 chat.id 字符串命中,再按 chat.username 匹配(忽略大小写);

    未命中返回 None。
    """
    if requested is None or not chats_by_id:
        return None
    stripped: Any
    if isinstance(requested, bool):
        # bool 是 int 子类,但不应被视为 chat_id
        return None
    if isinstance(requested, int):
        stripped = str(requested)
        return stripped if stripped in chats_by_id else None
    if isinstance(requested, str):
        s = requested.strip().lstrip("@")
        if not s:
            return None
        if s in chats_by_id:
            return s
        for cid, chat in chats_by_id.items():
            username = chat.get("username")
            if isinstance(username, str) and username.lower() == s.lower():
                return cid
    return None


_SLUG_RE = re.compile(r"[^\w\u4e00-\u9fff]+")


def _slugify(value: str, limit: int = 24) -> str:
    """把 chat 标题/用户名简化成 ASCII / 汉字 / 数字 / 下划线 形式,截断到 limit。"""
    slug = _SLUG_RE.sub("_", value or "").strip("_")
    return slug[:limit]


def generate_random_config_name(
    kind: NameGenKind,
    chat: Optional[Dict[str, Any]] = None,
    workdir: Optional[Path | str] = None,
) -> str:
    """生成一个未被占用的随机配置名,作为新建配置时的默认名称。

    - kind="signer" → ``sign_<slug>_<hex>``;kind="automation" → ``auto_<slug>_<hex>``
    - 末尾 ``<hex>`` 来自 ``secrets.token_hex``;16 位 hex 命名空间足够大,
      与已有配置冲突的概率可忽略。
    """
    prefix = CONFIG_KINDS[kind].name_prefix
    seed = ""
    if chat:
        seed = str(
            chat.get("title")
            or chat.get("username")
            or chat.get("first_name")
            or chat.get("id")
            or ""
        )
    slug = _slugify(seed) or "chat"
    if kind == "automation":
        existing = set(list_automation_names(workdir))
    else:
        existing = set(list_task_names(kind, workdir))
    name = f"{prefix}_{slug}_{secrets.token_hex(8)}"
    if name not in existing:
        return name
    return f"{prefix}_{slug}_{secrets.token_hex(16)}"


def load_config(
    kind: ConfigKind, name: str, workdir: Optional[Path | str] = None
) -> ConfigEntry:
    config_file = _config_path(kind, name, workdir)
    if not config_file.is_file():
        raise FileNotFoundError(f"配置不存在: {config_file}")
    cfg_cls = CONFIG_KINDS[kind].cfg_cls
    with open(config_file, "r", encoding="utf-8") as fp:
        raw = json.load(fp)
    cfg, from_old, err = cfg_cls.load_checked(raw)
    if cfg is None:
        raise ValueError(f"无法解析配置: {config_file}（{err or '未知原因'}）")
    if from_old:
        # keep the latest structure aligned with current schema
        save_config(kind, name, cfg, workdir=workdir)
    payload = cfg.to_jsonable()
    return ConfigEntry(
        name=name, path=config_file, updated_from_old=from_old, payload=payload, cfg=cfg
    )


def save_config(
    kind: ConfigKind,
    name: str,
    content: Dict[str, Any] | str | BaseJSONConfig,
    workdir: Optional[Path | str] = None,
) -> Path:
    cfg_cls = CONFIG_KINDS[kind].cfg_cls
    if isinstance(content, BaseJSONConfig):
        cfg = content
    else:
        data = json.loads(content) if isinstance(content, str) else content
        cfg, _from_old, err = cfg_cls.load_checked(data)
        if cfg is None:
            raise ValueError(err or "配置校验失败")
    config_file = _config_path(kind, name, workdir)
    config_file.parent.mkdir(parents=True, exist_ok=True)
    with open(config_file, "w", encoding="utf-8") as fp:
        json.dump(cfg.to_jsonable(), fp, ensure_ascii=False, indent=2)
    return config_file


def delete_config(
    kind: ConfigKind, name: str, workdir: Optional[Path | str] = None
) -> Path:
    config_file = _config_path(kind, name, workdir)
    if not config_file.exists():
        raise FileNotFoundError(f"配置不存在: {config_file}")
    # 删除整个配置目录(连同遗留 sign_record.json 等),保证删除后不再残留。
    # 签到记录主存储是 SQLite(data.sqlite3),不受影响。
    shutil.rmtree(config_file.parent, ignore_errors=True)
    return config_file


def load_user_infos(workdir: Optional[Path | str] = None) -> List[UserInfo]:
    base = get_workdir(workdir)
    users_dir = base / "users"
    if not users_dir.is_dir():
        return []
    entries: List[UserInfo] = []
    for user_dir in sorted(
        [p for p in users_dir.iterdir() if p.is_dir()], key=lambda p: p.name
    ):
        me_file = user_dir / "me.json"
        if not me_file.is_file():
            continue
        with open(me_file, "r", encoding="utf-8") as fp:
            try:
                data = json.load(fp)
            except json.JSONDecodeError:
                continue
        # me.json 里是合法 JSON 但不是对象时（手改成 null / []），下游按 dict
        # 取字段会 AttributeError / TypeError，把 /api/chats 打成 500。
        # 与 latest_chats.json 的非数组守卫同理：跳过该条目。
        if not isinstance(data, dict):
            continue

        latest_chats = []
        chats_file = user_dir / "latest_chats.json"
        if chats_file.is_file():
            with open(chats_file, "r", encoding="utf-8") as fp:
                try:
                    latest_chats = json.load(fp)
                except json.JSONDecodeError:
                    pass
        # 文件内容不保证是数组（手改过、或被截断成对象），下游按 list 迭代，
        # 直接透传会让 /api/chats 抛 TypeError 变 500。
        if not isinstance(latest_chats, list):
            latest_chats = []

        entries.append(
            UserInfo(
                user_id=user_dir.name,
                data=data,
                path=me_file,
                latest_chats=latest_chats,
            )
        )
    return entries


def _record_target(path: Path, signs_root: Path) -> Tuple[str, Optional[str]]:
    relative_parts = path.relative_to(signs_root).parts
    task = relative_parts[0]
    user_id = None
    if len(relative_parts) > 2:
        user_id = relative_parts[1]
    return task, user_id


def _record_dedup_key(
    path: Path, signs_root: Path, store: SignRecordStore
) -> Tuple[str, Optional[str]]:
    """计算 JSON 记录的去重键，必须与 SQLite 行的 (task, user_id) 对齐。

    老的 2 段布局 ``signs/<task>/sign_record.json`` 没有 user_id 段，
    ``_record_target`` 会给出 ``None``；而迁移到 SQLite 时
    ``SignRecordStore.resolve_record_target`` 会把它推断成当时唯一的 user_id。
    两边键不一致，同一个文件就会在 UI 里出现两次（「优先用已迁移的 SQLite 行」
    的去重注释因此形同虚设）。先问 store 要标准答案，拿不到再退回旧逻辑。
    """
    try:
        resolved = store.resolve_record_target(path)
    except ValueError:
        resolved = None
    if resolved is not None:
        return resolved
    return _record_target(path, signs_root)


def load_sign_records(workdir: Optional[Path | str] = None) -> List[SignRecord]:
    base = get_workdir(workdir)
    signs_dir = base / "signs"
    records: List[SignRecord] = []
    existing_keys: set[tuple[str, Optional[str]]] = set()

    store = SignRecordStore(base)
    if store.db_path.is_file():
        try:
            groups = store.list_record_groups()
        except sqlite3.Error as exc:
            # data.sqlite3 损坏（「file is not a database」）或被长时间锁住时，
            # 记录页不应该整个 500：退化成「只展示 JSON 记录」。
            logger.warning("读取 SQLite 签到记录失败，仅展示 JSON 记录: %s", exc)
            groups = []
        for group in groups:
            key = (group.task_name, group.user_id)
            existing_keys.add(key)
            records.append(
                SignRecord(
                    task=group.task_name,
                    user_id=group.user_id,
                    records=group.records,
                    path=store.db_path,
                )
            )

    if not signs_dir.is_dir():
        return records

    for record_file in sorted(signs_dir.rglob("sign_record.json")):
        try:
            with open(record_file, "r", encoding="utf-8") as fp:
                data = json.load(fp)
        except (json.JSONDecodeError, OSError):
            continue
        task, user_id = _record_dedup_key(record_file, signs_dir, store)
        key = (task, user_id)
        # Prefer the migrated SQLite rows when both sources exist so the same
        # task/user pair does not appear twice in the UI.
        if key in existing_keys:
            continue
        items: Iterable[Tuple[str, str]] = (
            data.items() if isinstance(data, dict) else []
        )
        sorted_items = sorted(items, key=lambda kv: kv[0], reverse=True)
        records.append(
            SignRecord(
                task=task, user_id=user_id, records=sorted_items, path=record_file
            )
        )
    return records


def tail_file(path: Path, limit: int = 200) -> List[str]:
    if not path.is_file():
        return []
    if limit <= 0:
        return []

    buffer: deque[str] = deque()
    chunk_size = 8192

    # Read from the end in chunks to avoid loading large files entirely.
    with open(path, "rb") as fp:
        fp.seek(0, os.SEEK_END)
        position = fp.tell()
        leftover = b""
        have_leftover = False
        first_chunk = True
        while position > 0 and len(buffer) < limit:
            read_size = min(chunk_size, position)
            position -= read_size
            fp.seek(position)
            chunk = fp.read(read_size)
            # ``data`` 跨块拼回同一行，因此被块边界劈开的 UTF-8 序列也能还原。
            data = chunk + leftover
            lines = data.split(b"\n")
            leftover = lines[0]
            have_leftover = True
            tail = lines[1:]
            if first_chunk:
                first_chunk = False
                # 文件以换行结尾时 split 会在末尾多出一个空串；它不是真实的空行，
                # 却会白占一个 limit 名额（limit=3 的 3 行文件只回 2 行 + 一条
                # 伪空行）。只丢文件末尾这一个空段，中间的空行是真实空行。
                if tail and tail[-1] == b"":
                    tail = tail[:-1]
            for line in reversed(tail):
                buffer.appendleft(line.decode("utf-8", errors="ignore").rstrip("\r"))
                if len(buffer) >= limit:
                    break

        # 走到文件头时 leftover 才是真正的一行（可能本身就是空行）；提前凑够
        # limit 而中断时它只是半行，此时 len(buffer) >= limit，不会追加。
        if len(buffer) < limit and have_leftover:
            buffer.appendleft(leftover.decode("utf-8", errors="ignore").rstrip("\r"))

    return list(buffer)


def _is_readable_log(base: Path, candidate: Path) -> bool:
    """该路径是否是通过 ``/api/logs?path=`` 能真正读到的日志文件。

    列表与读取必须用同一套形状规则（``resolve_log_under``：最多一层子目录 +
    ``.log`` 后缀），否则会出现「列得出来、一点就 400」的文件 —— 这正是
    commit e450719 修过的「列得出读不到」问题在更深一层目录上的翻版。
    """
    try:
        resolve_log_under(base, candidate)
    except ValueError:
        return False
    return True


def list_log_files(log_dir: Optional[Path | str] = None) -> List[Path]:
    base = Path(log_dir) if log_dir else LOG_DIR
    if not base.is_dir():
        return []
    # 必须递归:``webui/runner.py`` 把每个任务的子进程日志写到
    # ``<workdir>/logs/<kind>-<account>/tg-signer.log``(每个子进程独立
    # RotatingFileHandler,否则多个 handler 会互相截断同一个文件)。原来的
    # ``glob("*.log")`` 只看顶层,于是所有真正有内容的任务日志都列不出来,
    # 日志页只剩一个 0 字节的 ``tg-signer.log`` 顶着,表现为「整页空白」。
    files = [
        p for p in base.rglob("*.log") if p.is_file() and _is_readable_log(base, p)
    ]

    # 排序即「默认选中项」:非空的排前面,同级按 mtime 倒序,于是 ``files[0]``
    # 就是最值得先看的那个。顶层 ``tg-signer.log`` 只有在 WebUI「运行」页启动过
    # 任务后才有内容(靠 stdout 重定向写入),纯 CLI 签到时它是 0 字节 —— 按文件名
    # 排序会正好把它排到中间并被选成默认值,于是页面显示「暂无日志内容」。
    def _rank(path: Path) -> tuple:
        try:
            stat = path.stat()
        except OSError:
            return (1, 0.0, str(path))
        return (0 if stat.st_size else 1, -stat.st_mtime, str(path))

    return sorted(files, key=_rank)


def _resolve_log_path(
    log_path: Optional[Path | str] = None, log_dir: Optional[Path | str] = None
) -> Path:
    """解析日志路径,只允许 ``log_dir`` 下的文件。

    前端会把 ``/api/logs/files`` 返回的绝对路径回传,所以这里不能只收文件名;
    但也不能像以前那样原样返回 —— 否则 ``?path=<任意绝对路径>`` 就是一个任意
    文件读取原语(可读到 ``*.session_string`` / ``.openai_config.json``)。

    用 ``resolve_log_under`` 而非 ``resolve_within``:后者只允许直接子项,会把
    ``logs/<kind>-<account>/tg-signer.log`` 判成越界(0.10.4 收紧 P1-1 时的连带
    副作用),导致「文件能列出来但读不到」。``resolve_log_under`` 放宽到一层子目录
    并强制 ``.log`` 后缀,任意文件读取面没有变大。
    """
    root = Path(log_dir) if log_dir else LOG_DIR
    if not log_path:
        # 顶层 tg-signer.log 靠 stdout 重定向写入，纯 CLI 签到时是 0 字节；
        # 直接默认到它就是「日志页整页空白」。改为回退到 list_log_files() 的
        # 首个（非空 + 最新），没有任何日志文件时才回到主日志名。
        files = list_log_files(root)
        return files[0] if files else root / DEFAULT_LOG_FILE.name
    return resolve_log_under(root, log_path)


def load_logs(
    limit: int = 200,
    log_path: Optional[Path | str] = None,
    log_dir: Optional[Path | str] = None,
) -> Tuple[Path, List[str]]:
    path = _resolve_log_path(log_path, log_dir)
    return path, tail_file(path, limit=limit)


GROUP_CHAT_TYPES = {"basic", "group", "supergroup", "channel", "bot"}


def _normalize_chat_type(value: Any) -> str:
    """归一化对话类型名称。

    ``latest_chats.json`` 的 type 字段存在两种写法：WebUI 登录写入的是
    ``"bot"``，而 CLI 登录经 Pyrogram ``Object.default`` 序列化后写入的是
    ``"ChatType.BOT"``。这里统一取最后一段并转小写，使两种缓存都能识别。
    """
    text = str(value or "").strip()
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    return text.lower()


def load_group_chats(workdir: Optional[Path | str] = None) -> List[Dict[str, Any]]:
    """Aggregate group/channel info from all users' latest_chats.json, deduplicated by id."""
    seen: Dict[Any, Dict[str, Any]] = {}
    for info in load_user_infos(workdir):
        account = (
            info.data.get("first_name") or info.data.get("username") or info.user_id
        )
        for chat in info.latest_chats or []:
            if not isinstance(chat, dict):
                continue
            chat_type = _normalize_chat_type(chat.get("type"))
            if chat_type not in GROUP_CHAT_TYPES:
                continue
            chat_id = chat.get("id")
            if chat_id is None:
                continue
            seen.setdefault(
                chat_id, {**chat, "type": chat_type, "account": str(account)}
            )
    return sorted(
        seen.values(),
        key=lambda c: str(c.get("title") or c.get("username") or "").lower(),
    )


class UIState:
    """WebUI 共享 UI 状态(不依赖 NiceGUI,便于无 GUI 环境测试)。"""

    def __init__(
        self, workdir: Optional[Path | str] = None, *, create: bool = True
    ) -> None:
        self.workdir: Path = get_workdir(workdir or DEFAULT_WORKDIR, create=create)
        # 统一主日志:<workdir>/logs/<LOG_FILE_NAME>,与子进程共享同一份
        self.log_path: Path = self.workdir / "logs" / LOG_FILE_NAME
        self._initial_workdir = self.workdir.resolve()

    def allowed_workdir_roots(self) -> List[Path]:
        """可切换到的根目录列表,每次都重新读取,便于测试与嵌入方调整。"""
        raw = os.environ.get(WORKDIR_ROOTS_ENV, "").strip()
        if raw:
            roots = [Path(p).expanduser() for p in raw.split(os.pathsep) if p.strip()]
        else:
            roots = [self._initial_workdir.parent]
        return [root.resolve() for root in roots]

    def _check_workdir(self, target: Path) -> None:
        roots = self.allowed_workdir_roots()
        if any(target == root or root in target.parents for root in roots):
            return
        allowed = "、".join(str(root) for root in roots)
        raise ValueError(
            f"工作目录越界: {target};允许范围: {allowed}。"
            f"如需切换至其它位置,请设置环境变量 {WORKDIR_ROOTS_ENV}"
        )

    def set_workdir(self, path_str: str) -> None:
        candidate = Path(path_str).expanduser()
        absolute = candidate if candidate.is_absolute() else Path.cwd() / candidate
        # 先校验再 mkdir:否则越界路径会先被创建出来,构成目录创建原语。
        # 用 resolve() 后的路径做包含性判断,顺带挡掉指向根之外的软链。
        self._check_workdir(absolute.resolve())
        self.workdir = get_workdir(candidate)
        self.log_path = self.workdir / "logs" / DEFAULT_LOG_FILE.name

    def init_workdir(self, path_str: str) -> None:
        """按 CLI ``--workdir`` 设定初始工作目录。

        与 :meth:`set_workdir` 的区别是不走 ``allowed_workdir_roots`` 白名单：
        那条白名单约束的是「通过 WebUI 切工作目录」这个远程动作，而 CLI 操作者
        本来就拥有该机器的完整文件权限，不构成越权。同时要更新
        ``_initial_workdir``，否则工作目录选择器的可选根仍是旧默认值。
        """
        candidate = Path(path_str).expanduser()
        absolute = candidate if candidate.is_absolute() else Path.cwd() / candidate
        self.workdir = get_workdir(absolute)
        self.log_path = self.workdir / "logs" / DEFAULT_LOG_FILE.name
        self._initial_workdir = self.workdir.resolve()


# configure_logger 会先 clear() 全局 logger 的 handlers 再重建,而 WebUI 的
# 请求线程随时可能正在写日志(handler 被清空的瞬间记录会掉进 lastResort)。
# 串行化配置动作,避免和正在输出的线程抢同一个 logger。
_logger_setup_lock = threading.Lock()


def _setup_webui_logger(workdir: Path) -> None:
    """Configure file logging for the WebUI process itself.

    WebUI runs in-process for account login/listing operations; without this
    the WebUI process writes only to stderr and reboots wipe the audit trail.
    """
    from tg_signer.logger import configure_logger

    log_dir = workdir / "logs"
    log_file = log_dir / LOG_FILE_NAME
    with _logger_setup_lock:
        configure_logger(log_level="INFO", log_dir=log_dir, log_file=log_file)
