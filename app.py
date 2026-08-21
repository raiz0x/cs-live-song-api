import os
import hashlib
import subprocess
import sys
#import tempfile
import glob
'''import shutil
yt_dlp_path = shutil.which("yt-dlp")
cmd = [yt_dlp_path, ...]'''

from flask import Flask, request, jsonify, send_from_directory

subprocess.run([sys.executable, "-m", "pip", "install", "-U", "yt-dlp"], capture_output=True)

app = Flask(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MUSIC_DIR = os.path.join(BASE_DIR, "music")
COOKIES_FILE = os.path.join(BASE_DIR, "youtube_cookies.txt")
os.makedirs(MUSIC_DIR, exist_ok=True)

SOURCES = [
    ("scsearch1", "SoundCloud"),
    ("ytsearch1", "YouTube"),
]

def get_duration(filepath):
    cmd = ["ffprobe", "-v", "error", "-show_entries", "format=duration",
           "-of", "default=noprint_wrappers=1:nokey=1", filepath]
    result = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return round(float(result.stdout.strip()))
    except:
        return 180

def is_url(query):
    q = query.lower()
    return q.startswith(("http://", "https://", "www.")) or "youtube.com/" in q or "youtu.be/" in q or "soundcloud.com/" in q

@app.route("/play")
def play():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify({"error": "Missing query"}), 400

    #h = hashlib.md5(q.lower().encode()).hexdigest()
    wav_file = os.path.join(MUSIC_DIR, "stream_temp.wav") #wav_file = os.path.join(MUSIC_DIR, f"{h}_8k.wav")
    base_url = "http://5.188.183.163:8080" #base_url = request.host_url.rstrip("/").replace("http://", "https://") SAU fara .replace

    if os.path.exists(wav_file):
        os.remove(wav_file)
        '''dur = get_duration(wav_file)
        return jsonify({
            "url": f"{base_url}/music/{h}_8k.wav", #stream_temp.wav
            "title": q,
            "duration": dur,
            "source": "cache",
            "ready": True
        })'''

    #temp_fd, temp_base = tempfile.mkstemp(dir=MUSIC_DIR, prefix=f"{h}_")
    #os.close(temp_fd)
    #os.remove(temp_base)

    '''thread = threading.Thread(target=process_song, args=(q,))
    thread.start()

    return jsonify({
        "url": f"{base_url}/music/stream_temp.wav",
        "title": q,
        "duration": 180,
        "source": "processing",
        "ready": False
    })
    #SI OFF ASTEA DE JOS'''
    temp_base = os.path.join(MUSIC_DIR, "temp_download") #temp_base = os.path.join(MUSIC_DIR, f"{h}_temp")

    all_errors = []
    source_used = None
    temp_wav = None
    source_url = None

    for source_prefix, source_name in SOURCES:
        if is_url(q):
            clean_url = q if q.startswith(("http://", "https://")) else f"https://{q}"
            
            if "soundcloud.com" in clean_url.lower() and source_name != "SoundCloud":
                continue
            if ("youtube.com" in clean_url.lower() or "youtu.be" in clean_url.lower()) and source_name != "YouTube":
                continue
            
            target_input = clean_url
        else:
            target_input = f"{source_prefix}:{q}"
        
        cmd = [
            "yt-dlp", # SAU /usr/local/bin/yt-dlp
            "--no-check-certificate",
            "--user-agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "--no-playlist",
            "--max-downloads", "1",
            "--print", "webpage_url",
            "-x", "--audio-format", "wav", "--audio-quality", "0",
            "-o", f"{temp_base}.%(ext)s",
            target_input
        ]

        if source_name == "YouTube" and os.path.exists(COOKIES_FILE):
            cmd.extend(["--cookies", COOKIES_FILE]) #creca trba si pt file?

        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        except subprocess.TimeoutExpired:
            all_errors.append(f"{source_name}: timeout")
            continue

        #if result.returncode == 0 and os.path.exists(f"{temp_base}.wav"):
        wav_files = glob.glob(f"{temp_base}*.wav")
        if wav_files: #result.returncode == 0 and wav_files SAU if result.returncode in (0, 101) and wav_files
            source_used = source_name
            temp_wav = wav_files[0]
            if result.stdout:
                source_url = result.stdout.strip().splitlines()[0]
            break
        else:
            err_snippet = result.stderr[:200] if result.stderr else "unknown error"
            all_errors.append(f"{source_name}: {err_snippet}")

    if not source_used:
        #print(f"DEBUG: all_errors = {all_errors}")
        for f in glob.glob(f"{temp_base}*"):
            if os.path.exists(f):
                os.remove(f)
        return jsonify({
            "error": "Download failed",
            "sources_tried": [s[1] for s in SOURCES],
            "debug": " | ".join(all_errors)
        }), 500

    cmd = [
        "ffmpeg", "-y", "-i", temp_wav,
        "-ar", "8000", "-ac", "1", "-acodec", "pcm_s16le", #48000
        "-af", "volume=0.5", #nou | loudnorm=I=-20:TP=-2:LRA=11 + ,volume ?
        wav_file
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

    if os.path.exists(temp_wav):
        os.remove(temp_wav)

    if result.returncode != 0 or not os.path.exists(wav_file):
        if os.path.exists(wav_file):
            os.remove(wav_file)
        return jsonify({"error": "Conversion failed", "debug": result.stderr}), 500

    dur = get_duration(wav_file)

    return jsonify({
        "url": f"{base_url}/music/stream_temp.wav", #{base_url}/music/{h}_8k.wav
        "title": q,
        "duration": dur,
        "source": source_used,
        "source_url": source_url,
        "size_mb": round(os.path.getsize(wav_file) / 1024 / 1024, 2),
        "created": os.path.getctime(wav_file),
        "modified": os.path.getmtime(wav_file)
    })

@app.route("/music/<path:filename>")
def serve_music(filename):
    filepath = os.path.join(MUSIC_DIR, filename)
    if not os.path.exists(filepath):
        return jsonify({"error": "File not found", "path": filepath, "ready": False}), 404
    return send_from_directory(MUSIC_DIR, filename)

@app.route("/debug")
def debug():
    files = []
    if os.path.exists(MUSIC_DIR):
        for f in os.listdir(MUSIC_DIR):
            path = os.path.join(MUSIC_DIR, f)
            if os.path.isfile(path):
                files.append({
                    "name": f,
                    "size_mb": round(os.path.getsize(path) / 1024 / 1024, 2),
                    "created": os.path.getctime(path),
                    "modified": os.path.getmtime(path)
                })
    return jsonify({
        "music_dir": MUSIC_DIR,
        "exists": os.path.exists(MUSIC_DIR),
        "files": files
    })

@app.route("/test")
def test():
    result = subprocess.run(["yt-dlp", "--version"], capture_output=True, text=True)
    return jsonify({"version": result.stdout.strip(), "error": result.stderr})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080, debug=True)
