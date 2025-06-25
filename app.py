import os
import subprocess
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import sys

# --- App Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Storage & State Configuration ---
VOLUME_PATH = '/data'
VIDEO_STORAGE_PATH = os.path.join(VOLUME_PATH, 'videos')
if not os.path.exists(VIDEO_STORAGE_PATH):
    os.makedirs(VIDEO_STORAGE_PATH)

# চলমান স্ট্রিমগুলোর তথ্য রাখার জন্য একটি গ্লোবাল ডিকশনারি
# Key: filename, Value: subprocess.Popen object
running_streams = {}

# --- Helper Functions ---
def start_ffmpeg_process(video_path, rtmp_url):
    command = [
        'ffmpeg', '-re', '-stream_loop', '-1', '-i', video_path,
        '-c:v', 'libx264', '-preset', 'veryfast', '-maxrate', '3000k',
        '-bufsize', '6000k', '-pix_fmt', 'yuv420p', '-g', '50',
        '-c:a', 'aac', '-b:a', '128k', '-ar', '44100',
        '-f', 'flv', rtmp_url
    ]
    # FFmpeg প্রসেসটিকে সম্পূর্ণ ব্যাকগ্রাউন্ডে চালানো
    process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    return process

def stop_ffmpeg_process(process):
    if process:
        process.terminate() # FFmpeg প্রসেসটি বন্ধ করা
        try:
            process.wait(timeout=5) # প্রসেসটি বন্ধ হওয়ার জন্য ৫ সেকেন্ড অপেক্ষা করা
        except subprocess.TimeoutExpired:
            process.kill() # যদি বন্ধ না হয়, তাহলে জোর করে বন্ধ করা
        return True
    return False

# --- Routes ---
@app.route('/')
def health_check():
    return jsonify({"status": "ok", "message": "Backend v6 (Stateful Streaming) is running!"})

@app.route('/upload', methods=['POST'])
def upload_video():
    # এই অংশটি অপরিবর্তিত
    try:
        if 'video' not in request.files or 'uid' not in request.form:
            return jsonify({"error": "Missing video file or user ID."}), 400
        video_file = request.files['video']
        uid = request.form.get('uid')
        if video_file.filename == '':
            return jsonify({"error": "No selected file."}), 400
        filename = f"{uid}__{secure_filename(video_file.filename)}"
        save_path = os.path.join(VIDEO_STORAGE_PATH, filename)
        video_file.save(save_path)
        return jsonify({"message": "Video uploaded successfully!", "filename": filename}), 200
    except Exception as e:
        logging.error(f"Error in /upload: {e}", exc_info=True)
        return jsonify({"error": "Internal server error during upload."}), 500

@app.route('/videos/<uid>', methods=['GET'])
def get_videos(uid):
    # এই অংশটি অপরিবর্তিত
    try:
        user_videos = []
        for filename in os.listdir(VIDEO_STORAGE_PATH):
            if filename.startswith(f"{uid}__"):
                original_name = filename.split('__', 1)[1]
                user_videos.append({"id": filename, "name": original_name})
        return jsonify(user_videos), 200
    except Exception as e:
        logging.error(f"Error in /videos: {e}", exc_info=True)
        return jsonify({"error": "Could not list videos."}), 500

@app.route('/stream/start', methods=['POST'])
def start_stream():
    try:
        filename = request.form.get('filename')
        if filename in running_streams:
            return jsonify({"error": "This video is already streaming."}), 409

        stream_url = request.form.get('stream_url')
        stream_key = request.form.get('stream_key')
        if not all([filename, stream_url, stream_key]):
            return jsonify({"error": "Missing required streaming parameters."}), 400
        
        video_path = os.path.join(VIDEO_STORAGE_PATH, filename)
        if not os.path.exists(video_path):
             return jsonify({"error": f"Video file not found: {filename}"}), 404

        full_rtmp_url = f"{stream_url.strip()}/{stream_key.strip()}"
        process = start_ffmpeg_process(video_path, full_rtmp_url)
        running_streams[filename] = process
        
        logging.info(f"Stream started for '{filename}'. Process ID: {process.pid}")
        return jsonify({"message": f"Stream for '{filename}' has started successfully!"}), 200
    except Exception as e:
        logging.error(f"Error in /stream/start: {e}", exc_info=True)
        return jsonify({"error": "Internal server error while starting stream."}), 500

@app.route('/stream/stop', methods=['POST'])
def stop_stream():
    try:
        filename = request.form.get('filename')
        if filename not in running_streams:
            return jsonify({"error": "Stream not found or already stopped."}), 404
        
        process = running_streams.pop(filename) # তালিকা থেকে মুছে ফেলা
        if stop_ffmpeg_process(process):
            logging.info(f"Stream stopped for '{filename}'.")
            return jsonify({"message": f"Stream for '{filename}' has been stopped."}), 200
        else:
            return jsonify({"error": "Could not stop the stream process."}), 500
    except Exception as e:
        logging.error(f"Error in /stream/stop: {e}", exc_info=True)
        return jsonify({"error": "Internal server error while stopping stream."}), 500

@app.route('/stream/status', methods=['GET'])
def stream_status():
    # বর্তমানে কোন কোন ভিডিও লাইভ চলছে তার তালিকা পাঠানো
    active_streams = list(running_streams.keys())
    return jsonify({"active_streams": active_streams}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
