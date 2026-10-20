from pyrogram import raw

try:
    from pyrogram.types import AnimatedChatPhoto
except ImportError:  # Kurigram versions before AnimatedChatPhoto was introduced.
    AnimatedChatPhoto = None


def patch_animated_chat_photo_parser() -> None:
    """Ignore animated photos without a usable video representation.

    Kurigram 2.2.25 checks that ``photo.video_sizes`` is non-empty, but then
    calls ``max()`` after filtering the list to ``VideoSize`` instances. A
    photo containing only markup entries therefore raises ``ValueError``.
    """
    if AnimatedChatPhoto is None:
        return

    original_parse = AnimatedChatPhoto._parse

    async def safe_parse(client, photo):
        if isinstance(photo, raw.types.Photo) and not any(
            isinstance(video_size, raw.types.VideoSize)
            for video_size in photo.video_sizes or []
        ):
            return None

        return await original_parse(client, photo)

    AnimatedChatPhoto._parse = staticmethod(safe_parse)
