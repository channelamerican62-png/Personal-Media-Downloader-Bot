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

def extract_urls(text: str):
    if not text:
        return []
    return URL_REGEX.findall(text)

def get_media_info(url: str):
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'skip_download': True,
        'extract_flat': False
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
    """
    Download video with smart Telegram 50MB limit adaptation.
    quality options: 'auto', '720p', '480p', '360p'
    """
    out_template = str(DOWNLOADS_DIR / f"{user_id}_video_%(id)s.%(ext)s")
    
    # Format selection string based on quality
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
        'concurrent_fragment_downloads': 8, # 8x Multi-threaded chunk downloads
        'buffersize': 1048576, # 1MB buffer for fast streaming
    }
    if FFMPEG_PATH:
        ydl_opts['ffmpeg_location'] = FFMPEG_PATH

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        try:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            
            # Check for merged mp4
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
            
            # Telegram 50MB check (49MB max for safety)
            if filesize > 49 * 1024 * 1024 and quality != "360p":
                # Fallback to lower resolution
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
    """Extract and download MP3 audio."""
    out_template = str(DOWNLOADS_DIR / f"{user_id}_audio_%(id)s.%(ext)s")
    
    ydl_opts = {
        'format': 'bestaudio/best',
        'outtmpl': out_template,
        'quiet': True,
        'no_warnings': True,
        'concurrent_fragment_downloads': 8,
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
