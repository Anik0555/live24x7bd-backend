import os
import subprocess
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)
CORS(app, resources={r"/stream": {"origins": "*"}})

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'mkv', 'avi'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024  # 1 GB limit

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def check_ffmpeg():
    try:
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logging.info("FFmpeg is installed and accessible.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.error("FFmpeg not found. Please install FFmpeg and ensure it's in your system's PATH.")
        return False

FFMPEG_AVAILABLE = check_ffmpeg()

# Health Check Endpoint
@app.route('/')
def health_check():
    return jsonify({"status": "ok", "message": "Backend is running!"})

@app.route('/stream', methods=['POST'])
def start_stream():
    if not FFMPEG_AVAILABLE:
        return jsonify({"error": "FFmpeg is not installed on the server. Cannot start stream."}), 500

    if 'video' not in request.files:
        return jsonify({"error": "No video file part in the request"}), 400
    
    file = request.files['video']
    stream_url = request.form.get('stream_url') # নতুন যোগ করা হয়েছে
    stream_key = request.form.get('stream_key')

    if not stream_key or not stream_url: # নতুন যোগ করা হয়েছে
        return jsonify({"error": "No stream URL or key provided"}), 400
        
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            file.save(video_path)
            logging.info(f"File '{filename}' saved successfully.")

            # Construct the full RTMP URL by combining Stream URL and Stream Key
            # This is the correct way to stream to YouTube.
            full_rtmp_url = f"{stream_url}/{stream_key}" # নতুন যোগ করা হয়েছে
            
            command = [
                'ffmpeg',
                '-re',
                '-stream_loop', '-1',
                '-i', video_path,
                '-c:v', 'copy',
                '-c:a', 'copy',
                '-f', 'flv',
                full_rtmp_url # পরিবর্তিত
            ]
            
            logging.info(f"Starting FFmpeg with command: {' '.join(command)}")
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            return jsonify({"message": f"Stream for '{filename}' has been started successfully!"}), 200

        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return jsonify({"error": f"An internal server error occurred: {e}"}), 500

    else:
        return jsonify({"error": "File type not allowed."}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
