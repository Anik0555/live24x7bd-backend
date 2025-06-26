import os
import subprocess
import logging
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import sys
import atexit

# --- App Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s', stream=sys.stdout)
app = Flask(__name__)
CORS(app, resources={r"/*": {"origins": "*"}})

# --- Storage & State Configuration ---
# Render-এর Persistent Disk /data-তে মাউন্ট করা হয়েছে
VOLUME_PATH = '/data' 
VIDEO_STORAGE_PATH = os.path.join(VOLUME_PATH, 'videos')
if not os.path.exists(VIDEO_STORAGE_PATH):
    os.makedirs(VIDEO_STORAGE_PATH)
    logging.info(f"Created video storage directory at: {VIDEO_STORAGE_PATH}")

# Key: slot_id (e.g., 'slot-1'), Value: { 'process': Popen object, 'filename': 'video.mp4' }
running_streams = {}

# --- Helper Functions ---
def cleanup_process(process):
    """Safely terminate a running FFmpeg process."""
    if process and process.poll() is None:
        logging.info(f"Terminating FFmpeg process {process.pid}")
        process.terminate()
        try:
            process.wait(timeout=5)
            logging.info(f"Process {process.pid} terminated gracefully.")
        except subprocess.TimeoutExpired:
            logging.warning(f"Process {process.pid} did not terminate gracefully, killing.")
            process.kill()

@atexit.register
def cleanup_all_streams():
    """Ensure all FFmpeg processes are terminated when the app exits or restarts."""
    logging.info("Application shutting down. Cleaning up all active streams.")
    for slot_id, stream_info in list(running_streams.items()):
        logging.info(f"Stopping stream for {slot_id} on shutdown.")
        cleanup_process(stream_info.get('process'))

# --- Routes ---
@app.route('/')
def health_check():
    return jsonify({"status": "ok", "message": "Backend v11 (Final Multi-Stream) is running!"})

@app.route('/stream/start', methods=['POST'])
def start_stream():
    try:
        # FormData থেকে ডেটা গ্রহণ
        slot_id = request.form.get('slot_id')
        video_file = request.files.get('video')
        stream_url = request.form.get('stream_url')
        stream_key = request.form.get('stream_key')

        if not all([slot_id, video_file, stream_url, stream_key]):
            return jsonify({"error": "Missing required parameters (slot_id, video, stream_url, stream_key)."}), 400

        if slot_id in running_streams and running_streams[slot_id]['process'].poll() is None:
            return jsonify({"error": f"Slot {slot_id} is already streaming."}), 409

        # ভিডিও ফাইলটি সেভ করা
        filename = f"{slot_id}__{secure_filename(video_file.filename)}"
        video_path = os.path.join(VIDEO_STORAGE_PATH, filename)
        video_file.save(video_path)
        logging.info(f"Video for {slot_id} saved to {video_path}")

        # FFmpeg কমান্ড তৈরি এবং চালু করা (আলট্রা ফাস্ট)
        full_rtmp_url = f"{stream_url.strip()}/{stream_key.strip()}"
        command = ['ffmpeg', '-re', '-stream_loop', '-1', '-i', video_path, '-c', 'copy', '-f', 'flv', full_rtmp_url]
        
        process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        
        # চলমান স্ট্রিমের তথ্য সেভ করা
        running_streams[slot_id] = {'process': process, 'filename': filename}
        
        logging.info(f"Stream started for {slot_id} with video {filename}. PID: {process.pid}")
        return jsonify({"message": f"Stream for Slot {slot_id.split('-')[1]} has started successfully!"}), 200

    except Exception as e:
        logging.error(f"Error in /stream/start: {e}", exc_info=True)
        return jsonify({"error": "Internal server error while starting stream."}), 500

@app.route('/stream/stop', methods=['POST'])
def stop_stream():
    try:
        slot_id = request.form.get('slot_id')
        if not slot_id:
            return jsonify({"error": "Missing slot_id."}), 400

        stream_info = running_streams.pop(slot_id, None)
        if not stream_info:
            return jsonify({"error": "Stream not found or already stopped."}), 404
        
        # স্ট্রিম প্রসেসটি বন্ধ করা
        cleanup_process(stream_info['process'])
        logging.info(f"Stream stopped for {slot_id}.")

        # ভিডিও ফাইলটি সার্ভার থেকে ডিলিট করা
        video_path = os.path.join(VIDEO_STORAGE_PATH, stream_info['filename'])
        if os.path.exists(video_path):
            os.remove(video_path)
            logging.info(f"Deleted video file: {video_path}")

        return jsonify({"message": f"Stream for Slot {slot_id.split('-')[1]} has been stopped."}), 200
    except Exception as e:
        logging.error(f"Error in /stream/stop: {e}", exc_info=True)
        return jsonify({"error": "Internal server error while stopping stream."}), 500

@app.route('/stream/status', methods=['GET'])
def stream_status():
    active_streams = []
    # চেক করা যে কোন কোন প্রসেস এখনো চলছে
    for slot_id, stream_info in list(running_streams.items()):
        if stream_info['process'].poll() is None:
            active_streams.append(slot_id)
        else:
            # যদি কোনো স্ট্রিম নিজে থেকে বন্ধ হয়ে যায়, তাহলে তালিকা থেকে মুছে ফেলা
            logging.info(f"Stream for {slot_id} found to be finished. Cleaning up.")
            del running_streams[slot_id]
            
    return jsonify({"active_streams": active_streams}), 200

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
