from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton


def create_main_keyboard(
    qualities: list[int] | None = None,
    service: str = "youtube",
    include_playlist: bool = True,
) -> InlineKeyboardMarkup:
    keyboard: list[list[InlineKeyboardButton]] = []

    if service == "soundcloud":
        keyboard.append(
            [
                InlineKeyboardButton(
                    text="🎧 Download SoundCloud Track",
                    callback_data="download_audio",
                )
            ]
        )
        if include_playlist:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text="📝 Download SoundCloud Playlist",
                        callback_data="download_sc_playlist",
                    )
                ]
            )
    elif service in {"instagram", "tiktok", "twitter"}:
        labels = {
            "instagram": "📸 Download Instagram Media",
            "tiktok": "🎬 Download TikTok Video",
            "twitter": "🐦 Download Twitter Video",
        }
        audio_callbacks = {
            "tiktok": "download_tiktok_audio",
            "twitter": "download_twitter_audio"
        }
        
        keyboard.append(
            [
                InlineKeyboardButton(
                    text=labels[service],
                    callback_data=f"download_video:{service}",
                )
            ]
        )
        
        # Add audio download button for TikTok and Twitter
        if service in audio_callbacks:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text="🎵 Download Audio (MP3)",
                        callback_data=audio_callbacks[service]
                    )
                ]
            )
    else:
        video_label_prefix = "📹 Video"
        playlist_label_prefix = "📝 Playlist"

        if qualities:
            for quality in qualities:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            text=f"{video_label_prefix} ({quality}p)",
                            callback_data=f"download_video:{quality}",
                        )
                    ]
                )
            if include_playlist:
                for quality in qualities:
                    keyboard.append(
                        [
                            InlineKeyboardButton(
                                text=f"{playlist_label_prefix} Video ({quality}p)",
                                callback_data=f"download_playlist_video:{quality}",
                            )
                        ]
                    )
        else:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text=f"{video_label_prefix} (Best Available)",
                        callback_data="download_video:best",
                    )
                ]
            )
            if include_playlist:
                keyboard.append(
                    [
                        InlineKeyboardButton(
                            text=f"{playlist_label_prefix} Video (Best)",
                            callback_data="download_playlist_video:best",
                        )
                    ]
                )

        keyboard.append(
            [InlineKeyboardButton(text="🎵 Download Audio (MP3)", callback_data="download_audio")]
        )
        if include_playlist:
            keyboard.append(
                [
                    InlineKeyboardButton(
                        text="🎵 Playlist Audio",
                        callback_data="download_playlist",
                    )
                ]
            )

    keyboard.append(
        [InlineKeyboardButton(text="📝 Guide", callback_data="help")]
    )
    keyboard.append(
        [InlineKeyboardButton(text="❌ Cancel", callback_data="back_to_menu")]
    )

    return InlineKeyboardMarkup(inline_keyboard=keyboard)


def create_back_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="back_to_menu")]
        ]
    )


def create_help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 Back to Menu", callback_data="close_help")]
        ]
    )
