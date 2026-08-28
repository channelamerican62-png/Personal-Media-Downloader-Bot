import os
import re
import glob
import logging
from pathlib import Path
import yt_dlp

try:
    import imageio_ffmpeg
    FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
except Exception:
    FFMPEG_PATH = None

DOWNLOADS_DIR = Path(__file__).parent / "downloads"
DOWNLOADS_DIR.mkdir(exist_ok=True)

URL_REGEX = re.compile(
    r'(https?://(?:www\.|(?!www))[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|www\.[a-zA-Z0-9][a-zA-Z0-9-]+[a-zA-Z0-9]\.[^\s]{2,}|https?://[^\s]+)'
)

# Base YouTube bypass arguments (Android/iOS client spoofing to bypass cloud IP bot checks)
YOUTUBE_EXTRACTOR_ARGS = {
    'youtube': {
        'player_client': ['android', 'ios'],
    }
}

DEFAULT_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1',
    'Accept-Language': 'en-US,en;q=0.9',
}

def extract_urls(text: str):
    if not text:
        return []
    return URL_REGEX.findall(text)

def get_media_info(url: str):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False,
        'extractor_args': YOUTUBE_EXTRACTOR_ARGS,
        'http_headers': DEFAULT_HEADERS
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=False)
            if not info:
                return {'error': 'Malumot olib bolmadi'}
            return {
                'title': info.get('title', 'Media'),
                'uploader': info.get('uploader') or info.get('channel') or 'Nomalum',
                'duration': info.get('duration', 0),
                'thumbnail': info.get('thumbnail', None),
                'filesize_approx': info.get('filesize_approx', 0)
            }
        except Exception as e:
            return {'error': str(e)}

def download_video(url: str, user_id: int, quality: str = "auto"):
    out_template = str(DOWNLOADS_DIR / f"{user_id}_video_%(id)s.%(ext)s")
    
    if quality == "480p":
        fmt = 'bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[height<=480][ext=mp4]/best[height<=480]/18/best'
    elif quality == "360p":
        fmt = 'bestvideo[height<=360][ext=mp4]+bestaudio[ext=m4a]/best[height<=360][ext=mp4]/best[height<=360]/18/best'
    elif quality == "720p":
        fmt = 'bestvideo[height<=720][filesize<?45M][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][filesize<?45M][ext=mp4]/best[filesize<?45M]/18/best'
    else: # auto
        fmt = 'bestvideo[height<=720][filesize<?45M][ext=mp4]+bestaudio[ext=m4a]/best[height<=720][filesize<?45M][ext=mp4]/bestvideo[height<=480][ext=mp4]+bestaudio[ext=m4a]/best[filesize<?45M]/18/best'

    ydl_opts = {
        'format': fmt,
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'merge_output_format': 'mp4',
        'concurrent_fragment_downloads': 8,
        'buffersize': 1048576,
        'extractor_args': YOUTUBE_EXTRACTOR_ARGS,
        'http_headers': DEFAULT_HEADERS
    }
    if FFMPEG_PATH:
        ydl_opts['ffmpeg_location'] = FFMPEG_PATH

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            if not os.path.exists(filename):
                mp4_filename = os.path.splitext(filename)[0] + ".mp4"
                if os.path.exists(mp4_filename):
                    filename = mp4_filename
                else:
                    matches = glob.glob(str(DOWNLOADS_DIR / f"{user_id}_video_*"))
                    if matches:
                        filename = matches[0]

            if not os.path.exists(filename):
                return {'success': False, 'error': 'Fayl topilmadi.'}

            filesize = os.path.getsize(filename)
            
            if filesize > 49 * 1024 * 1024 and quality != "360p":
                cleanup_user_files(user_id)
                return download_video(url, user_id, quality="360p")

            return {
                'success': True,
                'file_path': filename,
                'title': info.get('title', 'Video'),
                'uploader': info.get('uploader') or info.get('channel') or 'Nomalum',
                'duration': info.get('duration', 0),
                'filesize': filesize
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

def download_audio(url: str, user_id: int):
    out_template = str(DOWNLOADS_DIR / f"{user_id}_audio_%(id)s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'concurrent_fragment_downloads': 8,
        'extractor_args': YOUTUBE_EXTRACTOR_ARGS,
        'http_headers': DEFAULT_HEADERS,
        'postprocessors': [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }],
    }
    if FFMPEG_PATH:
        ydl_opts['ffmpeg_location'] = FFMPEG_PATH

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            base_file = ydl.prepare_filename(info)
            mp3_file = os.path.splitext(base_file)[0] + ".mp3"
            
            if not os.path.exists(mp3_file):
                matches = glob.glob(str(DOWNLOADS_DIR / f"{user_id}_audio_*.mp3"))
                if matches:
                    mp3_file = matches[0]

            if not os.path.exists(mp3_file):
                return {'success': False, 'error': 'Audio konvertatsiya xatosi.'}

            return {
                'success': True,
                'file_path': mp3_file,
                'title': info.get('title', 'Musiqa'),
                'uploader': info.get('uploader') or info.get('channel') or 'Musiqa',
                'duration': info.get('duration', 0),
                'filesize': os.path.getsize(mp3_file)
            }
        except Exception as e:
            return {'success': False, 'error': str(e)}

def cleanup_user_files(user_id: int):
    pattern = str(DOWNLOADS_DIR / f"{user_id}_*")
    for f in glob.glob(pattern):
        try:
            os.remove(f)
        except Exception:
            pass
