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
    stream=sys.stdout  # Ensure logs go to standard output for Railway to capture
)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Storage Configuration ---
VOLUME_PATH = '/data'
VIDEO_STORAGE_PATH = os.path.join(VOLUME_PATH, 'videos')
if not os.path.exists(VIDEO_STORAGE_PATH):
    os.makedirs(VIDEO_STORAGE_PATH)
    logging.info(f"Created video storage directory at: {VIDEO_STORAGE_PATH}")

# --- Routes ---
@app.route('/')
def health_check():
    return jsonify({"status": "ok", "message": "Backend v4 (Railway Volume Storage - Debugging) is running!"})

@app.route('/upload', methods=['POST'])
def upload_video():
    try:
        if 'video' not in request.files or 'uid' not in request.form:
            return jsonify({"error": "Missing video file or user ID."}), 400
        video_file = request.files['video']
        uid = request.form.get('uid')
        if video_file.filename == '':
            return jsonify({"error": "No selected file."}), 400
        filename = f"{uid}__{secure_filename(video_file.filename)}"
        save_path = os.path.join(VIDEO_STORAGE_PATH, filename)
        logging.info(f"Saving video for user {uid} to {save_path}...")
        video_file.save(save_path)
        logging.info("Video saved successfully to volume.")
        return jsonify({"message": "Video uploaded successfully!", "filename": filename}), 200
    except Exception as e:
        logging.error(f"An error occurred in /upload: {e}", exc_info=True)
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

@app.route('/videos/<uid>', methods=['GET'])
def get_videos(uid):
    try:
        user_videos = []
        for filename in os.listdir(VIDEO_STORAGE_PATH):
            if filename.startswith(f"{uid}__"):
                original_name = filename.split('__', 1)[1]
                user_videos.append({"id": filename, "name": original_name})
        return jsonify(user_videos), 200
    except Exception as e:
        logging.error(f"An error occurred in /videos: {e}", exc_info=True)
        return jsonify({"error": f"Could not list videos: {str(e)}"}), 500

@app.route('/stream', methods=['POST'])
def start_stream():
    try:
        filename = request.form.get('filename')
        stream_url = request.form.get('stream_url')
        stream_key = request.form.get('stream_key')

        if not all([filename, stream_url, stream_key]):
            return jsonify({"error": "Missing required streaming parameters."}), 400
        
        video_path = os.path.join(VIDEO_STORAGE_PATH, filename)

        if not os.path.exists(video_path):
             return jsonify({"error": f"Video file not found on server: {filename}"}), 404

        logging.info(f"Attempting to start stream for video: {video_path}")
        
        full_rtmp_url = f"{stream_url.strip()}/{stream_key.strip()}"
        
        # আরও শক্তিশালী এবং সামঞ্জস্যপূর্ণ FFmpeg কমান্ড
        command = [
            'ffmpeg', '-re', '-stream_loop', '-1',
            '-i', video_path,
            '-c:v', 'libx264',         # ভিডিওকে H.264 ফরম্যাটে এনকোড করা
            '-preset', 'veryfast',     # কম CPU ব্যবহার করার জন্য
            '-maxrate', '2500k',       # সর্বোচ্চ বিটরেট (1080p এর জন্য ভালো)
            '-bufsize', '5000k',       # বাফারের আকার
            '-pix_fmt', 'yuv420p',     # সব ডিভাইসের সাথে সামঞ্জস্যপূর্ণ
            '-g', '60',                # Keyframe interval
            '-c:a', 'aac',             # অডিওকে AAC ফরম্যাটে এনকোড করা
            '-b:a', '128k',            # অডিও বিটরেট
            '-ar', '44100',            # অডিও স্যাম্পল রেট
            '-f', 'flv',
            full_rtmp_url
        ]
        
        logging.info(f"Executing FFmpeg command: {' '.join(command)}")
        
        # FFmpeg প্রসেসটি চালু করা এবং এর আউটপুট সরাসরি লগে পাঠানো
        process = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)

        # এই কোডটি FFmpeg থেকে আসা প্রতিটি লাইন সরাসরি আমাদের Railway লগে প্রিন্ট করবে
        for line in process.stdout:
            logging.info(f"[FFMPEG] {line.strip()}")

        process.wait()
        logging.info(f"FFmpeg process finished with exit code {process.returncode}")

        if process.returncode != 0:
            raise Exception(f"FFmpeg failed with exit code {process.returncode}")

        return jsonify({"message": f"Stream for '{filename}' has finished."}), 200 # Note: This will only return after stream ends

    except Exception as e:
        logging.error(f"An error occurred in /stream: {e}", exc_info=True)
        return jsonify({"error": f"An internal server error occurred: {str(e)}"}), 500

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
