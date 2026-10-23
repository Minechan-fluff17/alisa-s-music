import re
import requests
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
from telegram import (
    Update,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    filters,
    ContextTypes,
)
from telegram.request import HTTPXRequest
from googleapiclient.discovery import build
import asyncio
import os
from html import escape
from difflib import SequenceMatcher
from urllib.parse import urlencode

# === Flask для keep_alive ===
from flask import Flask
from threading import Thread

app_flask = Flask(__name__)


@app_flask.route('/')
def home():
    return "Bot is alive!"


def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_flask.run(host="0.0.0.0", port=port)


def keep_alive():
    t = Thread(target=run_flask)
    t.start()


# === API ключі ===
TELEGRAM_TOKEN_ENV = os.getenv("TELEGRAM_TOKEN_ENV", "TG_TOKEN")
TG_TOKEN = os.getenv(TELEGRAM_TOKEN_ENV)
SPOTIFY_ID = os.getenv("SPOTIFY_ID")
SPOTIFY_SECRET = os.getenv("SPOTIFY_SECRET")
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
CHANNEL_CHAT_ID = os.getenv("CHANNEL_CHAT_ID")

# === Підключення до Spotify ===
sp = spotipy.Spotify(auth_manager=SpotifyClientCredentials(
    client_id=SPOTIFY_ID, client_secret=SPOTIFY_SECRET))


def split_artist_and_title(query):
    """Parse the documented "Artist - Title" format, allowing uneven spacing."""
    match = re.match(r"^\s*(.+?)\s*-\s*(.+?)\s*$", query)
    if not match:
        return None, None
    return match.group(1).strip(), match.group(2).strip()


def normalize_music_text(value):
    return re.sub(r"[^\w]", "", value.casefold(), flags=re.UNICODE)


def title_similarity(expected, candidate):
    expected_normalized = normalize_music_text(expected)
    candidate_normalized = normalize_music_text(candidate)
    if not expected_normalized or not candidate_normalized:
        return 0
    if expected_normalized == candidate_normalized:
        return 1

    expected_words = set(re.findall(r"\w+", expected.casefold()))
    candidate_words = set(re.findall(r"\w+", candidate.casefold()))
    if expected_words and expected_words.issubset(candidate_words):
        # Accept common suffixes such as "Remastered" without losing the match.
        return 0.96
    return SequenceMatcher(None, expected_normalized, candidate_normalized).ratio()


def score_track_match(artist, title, candidate_artists, candidate_title):
    """Return a relevance score, rejecting same-title tracks by another artist."""
    normalized_artist = normalize_music_text(artist)
    artist_scores = [
        SequenceMatcher(
            None, normalized_artist, normalize_music_text(candidate_artist)
        ).ratio()
        for candidate_artist in candidate_artists
        if candidate_artist
    ]
    artist_score = max(artist_scores, default=0)
    title_score = title_similarity(title, candidate_title)

    # The artist is essential: a title-only match can point to an unrelated song.
    if artist_score < 0.7 or title_score < 0.72:
        return None
    return artist_score * 0.6 + title_score * 0.4


def search_spotify_track(artist, title):
    """Search multiple ways, then rank candidates by both artist and track title."""
    queries = (
        f"artist:{artist} track:{title}",
        f"{artist} {title}",
    )
    candidates = {}
    search_errors = []
    for search_query in queries:
        try:
            response = sp.search(q=search_query, limit=10, type="track")
            for track in response["tracks"]["items"]:
                candidates[track["id"]] = track
        except Exception as e:
            search_errors.append(e)
            print(f"❌ Spotify search error for {search_query!r}: {e}")

    if len(search_errors) == len(queries):
        raise search_errors[-1]

    ranked = []
    for track in candidates.values():
        artists = [item["name"] for item in track.get("artists", [])]
        score = score_track_match(artist, title, artists, track.get("name", ""))
        if score is not None:
            ranked.append((score, track))
    if not ranked:
        return None
    return max(ranked, key=lambda result: result[0])[1]


# === Пошук відео на YouTube ===
def search_youtube(query, artist_hints=None):
    try:
        artist, title = split_artist_and_title(query)

        youtube = build(
            "youtube",
            "v3",
            developerKey=YOUTUBE_API_KEY,
            static_discovery=False,
        )

        req = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            maxResults=25,
            order="relevance",
            videoCategoryId="10",
        )

        res = req.execute()
        items = res.get("items", [])

        if not items:
            return None, None

        # Якщо формат запиту не "Виконавець - Назва"
        if not artist or not title:
            video_id = items[0]["id"]["videoId"]
            return (
                f"https://www.youtube.com/watch?v={video_id}",
                video_id,
            )

        artist_terms = [
            normalize_music_text(part)
            for part in re.split(
                r"\s*,\s*|\s+&\s+|\s+feat(?:uring)?\.?\s+",
                artist,
                flags=re.IGNORECASE,
            )
            if part.strip()
        ]

        hint_terms = [
            normalize_music_text(hint)
            for hint in (artist_hints or [])
            if hint and hint.strip()
        ]
        channel_terms = [term for term in artist_terms + hint_terms if term]

        ranked = []

        for position, item in enumerate(items):
            snippet = item.get("snippet", {})
            video_title = snippet.get("title", "")
            channel = snippet.get("channelTitle", "")
            description = snippet.get("description", "")

            # Виконавець має бути в назві або на каналі (опис ігноруємо:
            # там часто згадують виконавця різні реакції й огляди)
            metadata = normalize_music_text(f"{video_title} {channel}")

            title_score = title_similarity(title, video_title)

            # Перевіряємо, чи збігається виконавець
            artist_matches = any(
                term and term in metadata
                for term in artist_terms
            )

            if title_score < 0.72 or not artist_matches:
                continue

            searchable = (
                f"{video_title} {channel}"
            ).casefold()

            # Відкидаємо нерелевантні версії
            if re.search(
                r"(react|reagi|reac[cç]|реакц|reakcj)"
                r"|\b(cover|review|ranking|rated|explained|breakdown|analysis|"
                r"karaoke|instrumental|sped up|slowed|nightcore|8d audio|"
                r"teaser|trailer|dance practice|choreography|"
                r"behind the scenes|making of|fancam|live|shorts)\b",
                searchable,
            ):
                continue

            # Пріоритет оригінальному кліпу
            if re.search(
                r"\b(music\s+video|video\s+clip|concept\s+video|"
                r"official\s+video|official\s+mv|official\s+m/v|mv|m/v)\b",
                searchable,
            ):
                video_type_rank = 3

            # Потім офіційному аудіо
            elif re.search(
                r"\b(official\s+audio|official\s+visualizer)\b",
                searchable,
            ):
                video_type_rank = 2

            # Далі lyric video та інші версії
            elif re.search(
                r"\b(lyric(s)?|visualizer|official)\b",
                searchable,
            ):
                video_type_rank = 1

            else:
                video_type_rank = 0

            score = (
                title_score
                + video_type_rank * 0.1
                - position * 0.001
            )

            # Відео з каналу самого виконавця (або VEVO) — найвищий пріоритет
            channel_normalized = normalize_music_text(channel)
            channel_is_official = int(
                "vevo" in channel_normalized
                or any(term in channel_normalized for term in channel_terms)
            )

            ranked.append(
                (channel_is_official, video_type_rank, score, item)
            )

        if not ranked:
            print(f"⚠️ YouTube: жоден результат не пройшов фільтри для {query!r}")
            return None, None

        selected = max(
            ranked,
            key=lambda result: (result[0], result[1], result[2]),
        )[3]

        video_id = selected["id"]["videoId"]

        return (
            f"https://www.youtube.com/watch?v={video_id}",
            video_id,
        )

    except Exception as e:
        print(f"❌ YouTube API error: {e}")
        return None, None


# === Пошук в Apple Music (через публічний iTunes Search API) ===
def search_apple_music(query, entity="song"):
    """Повертає посилання на Apple Music або None. entity: 'song' або 'album'."""
    try:
        term = query.replace(" - ", " ").strip()
        response = requests.get(
            "https://itunes.apple.com/search",
            params={"term": term, "entity": entity, "limit": 1},
            timeout=10,
        )
        response.raise_for_status()
        results = response.json().get("results", [])
        if not results:
            return None
        item = results[0]
        if entity == "album":
            return item.get("collectionViewUrl")
        return item.get("trackViewUrl")
    except Exception as e:
        print(f"❌ Apple Music search error: {e}")
        return None


# === Надсилання фінального посту з кнопками-посиланнями ===
async def send_music_post(
    chat_id,
    context,
    title,
    image_url,
    spotify_url=None,
    youtube_url=None,
    ytmusic_url=None,
    apple_music_url=None,
):
    # Якщо точне відео не знайдено — даємо посилання на пошук, щоб кнопка була завжди
    search_text = title.replace(" (альбом)", "")
    if not youtube_url:
        youtube_url = "https://www.youtube.com/results?" + urlencode(
            {"search_query": search_text}
        )
    if not ytmusic_url:
        ytmusic_url = "https://music.youtube.com/search?" + urlencode(
            {"q": search_text}
        )

    # Усі кнопки зі справжніми посиланнями (url=), без callback_data
    buttons = []

    if spotify_url:
        buttons.append(InlineKeyboardButton("🎧 Spotify", url=spotify_url))
    if youtube_url:
        buttons.append(InlineKeyboardButton("▶️ YouTube", url=youtube_url))
    if ytmusic_url:
        buttons.append(InlineKeyboardButton("🎶 YouTube Music", url=ytmusic_url))
    if apple_music_url:
        buttons.append(InlineKeyboardButton("🍎 Apple Music", url=apple_music_url))

    # Дві кнопки в рядку, щоб не були надто вузькими
    rows = [buttons[i:i + 2] for i in range(0, len(buttons), 2)]
    keyboard = InlineKeyboardMarkup(rows) if rows else None

    caption = f"🎵 <b>{escape(title)}</b>"

    try:
        await context.bot.send_photo(
            chat_id=chat_id,
            photo=image_url,
            caption=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )
    except Exception as e:
        # Якщо обкладинка не завантажилась — надсилаємо без неї
        print(f"❌ Помилка надсилання фото: {e}")
        await context.bot.send_message(
            chat_id=chat_id,
            text=caption,
            parse_mode="HTML",
            reply_markup=keyboard,
        )


# === Повідомлення з вибором: пісня чи альбом ===
async def send_choice_message(chat_id, context, query, reply_id=None):
    # Telegram обмежує callback_data до 64 байт
    if len(f"album|{query}".encode("utf-8")) > 64:
        await context.bot.send_message(
            chat_id=chat_id,
            text="⚠️ Запит задовгий, спробуй скоротити назву.",
            reply_to_message_id=reply_id,
        )
        return

    keyboard = InlineKeyboardMarkup([[
        InlineKeyboardButton("🎵 Пісня", callback_data=f"song|{query}"),
        InlineKeyboardButton("💿 Альбом", callback_data=f"album|{query}"),
    ]])

    await context.bot.send_message(
        chat_id=chat_id,
        text=f"Що шукати для «{query}»?",
        reply_markup=keyboard,
        reply_to_message_id=reply_id,
    )


# === Callback для вибору пісні або альбому ===
async def handle_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):

    cq = update.callback_query
    action, query = cq.data.split("|", 1)
    if action == "youtube":
        # Для старих inline-кнопок із callback_data шукаємо відео й
        # надсилаємо справжню URL-кнопку (callback-кнопка сама URL не відкриває).
        await cq.answer()
        youtube_url, video_id = search_youtube(query)
        if not youtube_url:
            if cq.message:
                await cq.message.reply_text(
                    f"Не вдалося знайти відео на YouTube: {query}"
                )
            return

        keyboard = InlineKeyboardMarkup([[
            InlineKeyboardButton("▶️ Відкрити відео на YouTube", url=youtube_url)
        ]])
        if cq.message:
            await cq.message.reply_text(
                f"Знайшов відео: {query}", reply_markup=keyboard
            )
        return

    await cq.answer()
    chat_id = cq.message.chat.id if cq.message else None  # додаємо перевірку на наявність message

    # Видаляємо повідомлення з кнопками
    try:
        if cq.message:
            await cq.message.delete()
        else:
            print("❌ Повідомлення не знайдено, неможливо видалити.")
    except Exception as e:
        print(f"❌ Помилка видалення повідомлення: {e}")

    try:
        # Ініціалізуємо посилання, щоб вони були визначені для обох гілок.
        youtube_url = None
        video_id = None
        ytmusic_url = None

        # === Пошук пісні ===
        if action == "song":
            artist, requested_title = split_artist_and_title(query)
            if not artist or not requested_title:
                await context.bot.send_message(chat_id, f"❌ Некоректний формат для пошуку: {query}")
                return

            track = search_spotify_track(artist, requested_title)
            if not track:
                platform_query = f"{artist} - {requested_title}"
                youtube_url, video_id = search_youtube(platform_query)
                if youtube_url:
                    keyboard = InlineKeyboardMarkup([[
                        InlineKeyboardButton(
                            "▶️ YouTube",
                            url=youtube_url,
                        ),
                        InlineKeyboardButton(
                            "🎶 YouTube Music",
                            url=f"https://music.youtube.com/watch?v={video_id}",
                        ),
                    ]])
                    message = (
                        "⚠️ У Spotify цієї пісні поки немає.\n"
                        f"Знайшов її на YouTube: {artist} — {requested_title}"
                    )
                else:
                    keyboard = None
                    message = (
                        "⚠️ У Spotify цієї пісні поки немає, і не вдалося "
                        f"автоматично знайти її на YouTube: {artist} — {requested_title}"
                    )
                await context.bot.send_message(
                    chat_id=chat_id,
                    text=message,
                    reply_markup=keyboard,
                )
                return

            artist_names = [item["name"] for item in track.get("artists", [])]
            resolved_artist = ", ".join(artist_names) or artist
            title = f"{resolved_artist} — {track['name']}"
            platform_query = f"{resolved_artist} - {track['name']}"
            spotify_url = track["external_urls"]["spotify"]
            image_url = track["album"]["images"][0]["url"]
            # Спочатку шукаємо за запитом користувача (коротким), бо список
            # усіх виконавців зі Spotify часто ламає пошук на YouTube
            youtube_url, video_id = search_youtube(
                f"{artist} - {requested_title}", artist_hints=artist_names
            )
            if not video_id:
                youtube_url, video_id = search_youtube(
                    platform_query, artist_hints=artist_names
                )
            if video_id:
                ytmusic_url = f"https://music.youtube.com/watch?v={video_id}"

            apple_music_url = search_apple_music(platform_query, entity="song")

        # === Пошук альбому ===
        else:
            res = sp.search(q=query, limit=1, type="album")
            if not res["albums"]["items"]:
                await context.bot.send_message(chat_id, f"❌ Альбом не знайдено: {query}")
                return

            album = res["albums"]["items"][0]
            title = f"{album['artists'][0]['name']} — {album['name']} (альбом)"
            platform_query = f"{album['artists'][0]['name']} - {album['name']}"
            spotify_url = album["external_urls"]["spotify"]
            image_url = album["images"][0]["url"]

            youtube_url, video_id = search_youtube(platform_query)

            ytmusic_url = (
                f"https://music.youtube.com/watch?v={video_id}"
                if video_id
                else None
            )

            apple_music_url = search_apple_music(platform_query, entity="album")

        await send_music_post(
            chat_id=chat_id,
            context=context,
            title=title,
            image_url=image_url,
            spotify_url=spotify_url,
            youtube_url=youtube_url,
            ytmusic_url=ytmusic_url,
            apple_music_url=apple_music_url,
        )

    except Exception as e:
        print(e)
        await context.bot.send_message(chat_id, "⚠️ Помилка під час пошуку")


# === Обробка повідомлень із тегом #music ===
async def handle_music(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message or update.channel_post
    if not message:
        return

    # Текст медіаповідомлення Telegram зберігає в caption, а не в text.
    message_text = message.text or message.caption
    if not message_text:
        return

    # Текст або підпис обробляємо однаково; саме вкладення не використовуємо.
    text = re.sub(r'\s+', ' ', message_text).strip()

    # Перевіряємо, чи є тег #music у тексті повідомлення
    if "#music" not in text.lower():
        return

    print("Received message with #music tag")
    print(f"Message text: {text}")

    # Знаходимо всі випадки, де є #music, а після нього — текст у дужках
    matches = re.findall(r"#music[^\n]*\(([^)]+)\)", text)

    if not matches:
        if update.message:
            await update.message.reply_text(
                "⚠️ Формат: #music (Artist - Title)"
            )
        return

    print(f"Matches found: {matches}")

    # Обробляємо кожен запит, знайдений у дужках
    for query in matches:
        await send_choice_message(
            chat_id=message.chat.id,
            context=context,
            query=query.strip(),
            reply_id=message.message_id
        )


# === /start команда ===
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message:
        await update.message.reply_text(
            "🎶 Надішли повідомлення з тегом #music і:\n\n"
            "📀 <b>Треки у дужках:</b>\n"
            "#music (IVE - Baddie)\n"
            "#music (Stray Kids - 5-STAR)\n\n"
            "Бот автоматично знайде пісню або альбом і надішле посилання на Spotify, YouTube, Apple Music!",
            parse_mode="HTML"
        )


# === Запуск бота ===
def main():
    if not TG_TOKEN:
        raise RuntimeError(
            f"Missing Telegram bot secret configured by {TELEGRAM_TOKEN_ENV}"
        )

    telegram_request = HTTPXRequest(
        connect_timeout=15,
        read_timeout=30,
        write_timeout=30,
        pool_timeout=15,
        media_write_timeout=60,
    )
    app = (
        Application.builder()
        .token(TG_TOKEN)
        .request(telegram_request)
        .build()
    )

    # Додаємо обробники для команд і повідомлень
    app.add_handler(CommandHandler("start", start))
    # Regex-фільтр PTB перевіряє текст, але не caption. Тому caption
    # пропускаємо окремо; handle_music відсіє підписи без #music.
    music_filter = (
        (filters.TEXT & filters.Regex(r"(?i)#music"))
        | filters.CAPTION
    )
    app.add_handler(
        MessageHandler(
            filters.UpdateType.MESSAGE & music_filter,
            handle_music,
        )
    )

    # Обробляємо натискання на кнопки вибору (пісня або альбом)
    app.add_handler(CallbackQueryHandler(handle_choice_callback))

    # Також обробляємо повідомлення з каналів
    app.add_handler(
        MessageHandler(
            filters.UpdateType.CHANNEL_POST & music_filter,
            handle_music,
        )
    )

    print("🚀 Бот запущений!")
    app.run_polling()


if __name__ == "__main__":
    keep_alive()
    main()
