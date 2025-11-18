# PuzikTubeBot

Telegram bot that downloads media from YouTube, SoundCloud, Spotify (via SpotDL), TikTok, Twitter/X, and Instagram. Drop a link — get the file.

## Features

- YouTube: video/audio with quality selection, playlists supported  
- SoundCloud: tracks & playlists  
- Spotify: tracks, albums, playlists, artists (SpotDL)  
- TikTok & Twitter/X: video/audio  
- Instagram: photos, videos, carousels (gallery-dl fallback)  
- Progress updates, concurrent download limits, automatic cleanup

## Requirements

- Python 3.11+ (tested on 3.13)  
- FFmpeg in PATH  
- `yt-dlp`, `spotdl`, `gallery-dl`, and dependencies from `requirements.txt`  
- Telegram bot token in `.env`

## Setup

### 1. Clone & Install
```bash
git clone https://github.com/Petyna/PuzikTubeBot.git
cd PuzikTubeBot
python -m venv venv
venv\Scripts\activate   # or source venv/bin/activate
pip install -r requirements.txt
```

### 2. Environment Config
- Copy `.env.example` → `.env`  
- Add your `BOT_TOKEN`

### 3. Optional
- Add `cookies.txt` or `instagram_cookies.txt` for private content

## Running

```bash
python main.py
```

The bot updates `yt-dlp`, starts cookie/cache managers, and begins polling.  
Stop with `Ctrl+C`. Temporary downloads are cleaned automatically.

## Usage

- Send a supported link and choose quality/format via the inline keyboard  
- Playlists may take longer — progress updates included  
- Spotify relies on SpotDL being configured correctly

## Troubleshooting

- **Missing BOT_TOKEN:** check `.env`  
- **FFmpeg errors:** install FFmpeg and ensure it’s in PATH  
- **SpotDL errors:** try running `spotdl` manually  
- **Cookies:** export cookies from your browser if needed

---

# Ukrainian Version

# PuzikTubeBot

Телеграм-бот, який уміє завантажувати медіа з YouTube, SoundCloud, Spotify (через SpotDL), TikTok, Twitter/X та Instagram. Даєш посилання — отримуєш файл.

## Можливості

- YouTube: відео/аудіо, вибір якості, плейлисти  
- SoundCloud: треки та плейлисти  
- Spotify: треки, альбоми, артисти, плейлисти (SpotDL)  
- TikTok + Twitter/X: відео та аудіо  
- Instagram: фото, відео, каруселі (fallback через gallery-dl)  
- Прогрес, ліміти на паралельні завантаження, автоочистка тимчасових файлів

## Необхідне

- Python 3.11+ (перевірено на 3.13)  
- FFmpeg у PATH  
- `yt-dlp`, `spotdl`, `gallery-dl` і залежності з `requirements.txt`  
- Токен бота у `.env`

## Установка

### 1. Клонування та інсталяція
```bash
git clone https://github.com/Petyna/PuzikTubeBot.git
cd PuzikTubeBot
python -m venv venv
venv\Scripts\activate   # або source venv/bin/activate
pip install -r requirements.txt
```

### 2. Налаштування оточення
- Скопіюй `.env.example` → `.env`  
- Вкажи `BOT_TOKEN`

### 3. Опційно
- Додай `cookies.txt` або `instagram_cookies.txt` для приватних постів

## Запуск

```bash
python main.py
```

Бот оновлює `yt-dlp`, піднімає менеджери кукі/кешу та починає polling.  
Зупинка — `Ctrl+C`. Тимчасові файли очищаються автоматично.

## Використання

- Надсилаєш посилання — обираєш формат та якість  
- Плейлисти можуть вантажитися довше, прогрес показується  
- Для Spotify потрібен правильно налаштований SpotDL

## Проблеми та рішення

- **Немає BOT_TOKEN:** перевір `.env`  
- **FFmpeg не працює:** додай у PATH  
- **Проблеми зі SpotDL:** перевір роботу `spotdl` вручну  
- **Кукі:** експортуй з браузера

