import os
import hashlib
import subprocess
import sys
import tempfile

from flask import Flask, request, jsonify, send_from_directory

subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"], capture_output=True)

app = Flask(__name__)

COOKIES_FILE = os.path.join(BASE_DIR, "youtube_cookies.txt")
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(BASE_DIR, "music")
os.makedirs(MUSIC_DIR, exist_ok=True)

SOURCES = [
    ("scsearch1", "SoundCloud"),
    ("bcsearch1", "Bandcamp"),
    ("dzsearch1", "Deezer"),
    ("ytsearch1", "YouTube"),
]

@app.route("/play")
def play():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Missing query"}), 400

    h = hashlib.md5(q.lower().encode()).hexdigest()
    wav_file = os.path.join(MUSIC_DIR, f"{h}_8k.wav")
    base_url = request.host_url.rstrip("/").replace("http://", "https://")

    if os.path.exists(wav_file):
        dur = get_duration(wav_file)
        return jsonify({
            "url": f"{base_url}/music/{h}_8k.wav",
            "title": q,
            "duration": dur
        })

    temp_fd, temp_base = tempfile.mkstemp(dir=MUSIC_DIR, prefix=f"{h}_")
    os.close(temp_fd)
    os.remove(temp_base)

    source_used = None
    for source_prefix, source_name in SOURCES:
        cmd = [
            "yt-dlp",
            "--no-check-certificate",
            "--user-agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "--cookies", COOKIES_FILE,
            "--no-playlist",
            "--max-downloads", "1",
            "-x", "--audio-format", "wav", "--audio-quality", "0",
            "-o", f"{temp_base}.%(ext)s",
            f"{source_prefix}:{q}"
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if result.returncode == 0 and os.path.exists(f"{temp_base}.wav"):
            source_used = source_name
            break

    if not source_used:
        for ext in [".wav", ".webm", ".m4a", ".mp3", ".part", ".opus", ".ogg"]:
            f = temp_base + ext
            if os.path.exists(f):
                os.remove(f)
        return jsonify({"error": "Download failed", "debug": result.stderr}), 500

    cmd = [
        "ffmpeg", "-y", "-i", f"{temp_base}.wav",
        "-ar", "8000", "-ac", "1", "-acodec", "pcm_s16le",
        wav_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if os.path.exists(f"{temp_base}.wav"):
        os.remove(f"{temp_base}.wav")

    if result.returncode != 0 or not os.path.exists(wav_file):
        if os.path.exists(wav_file):
            os.remove(wav_file)
        return jsonify({"error": "Conversion failed", "debug": result.stderr}), 500

    dur = get_duration(wav_file)

    return jsonify({
        "url": f"{base_url}/music/{h}_8k.wav",
        "title": q,
        "duration": dur
    })

@app.route("/music/<path:filename>")
def serve_music(filename):
    filepath = os.path.join(MUSIC_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found", "path": filepath}), 404
    return send_from_directory(MUSIC_DIR, filename)

@app.route("/debug")
def debug():
    files = os.listdir(MUSIC_DIR) if os.path.exists(MUSIC_DIR) else []
    return jsonify({
        "music_dir": MUSIC_DIR,
        "exists": os.path.exists(MUSIC_DIR),
        "files": files
    })

@app.route("/test")
def test():
    result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
    return jsonify({"version": result.stdout, "error": result.stderr})

def get_duration(filepath):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", filepath]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return round(float(result.stdout.strip()))
    except:
        return 180

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
