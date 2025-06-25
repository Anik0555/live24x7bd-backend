import os
import subprocess
from flask import Flask, request, jsonify
from flask_cors import CORS
from werkzeug.utils import secure_filename
import logging

# Configure logging
logging.basicConfig(level=logging.INFO)

app = Flask(__name__)

# Configure CORS to allow requests from your frontend's domain
# For development, you can allow all origins, but for production,
# you should restrict it to your actual frontend URL (e.g., 'https://your-app.netlify.app')
CORS(app, resources={r"/stream": {"origins": "*"}})

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'mp4', 'mov', 'mkv', 'avi'}
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 1 * 1024 * 1024 * 1024  # 1 GB limit

# Ensure the upload folder exists
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

def allowed_file(filename):
    """Checks if the file extension is allowed."""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def check_ffmpeg():
    """Checks if FFmpeg is installed and accessible."""
    try:
        # Use 'ffmpeg -version' which is a simple command to check existence and returns quickly.
        subprocess.run(['ffmpeg', '-version'], check=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        logging.info("FFmpeg is installed and accessible.")
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        logging.error("FFmpeg not found. Please install FFmpeg and ensure it's in your system's PATH.")
        return False

# Check for FFmpeg on startup
FFMPEG_AVAILABLE = check_ffmpeg()

@app.route('/stream', methods=['POST'])
def start_stream():
    """
    Receives a video file and a stream key, then starts an FFmpeg process
    to stream the video 24/7 to YouTube.
    """
    if not FFMPEG_AVAILABLE:
        return jsonify({"error": "FFmpeg is not installed on the server. Cannot start stream."}), 500

    # Check if the post request has the file part
    if 'video' not in request.files:
        return jsonify({"error": "No video file part in the request"}), 400
    
    file = request.files['video']
    stream_key = request.form.get('stream_key')

    # Basic validation
    if not stream_key:
        return jsonify({"error": "No stream key provided"}), 400
        
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400

    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        video_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        
        try:
            # Save the uploaded file
            file.save(video_path)
            logging.info(f"File '{filename}' saved successfully to '{video_path}'")

            # Construct the FFmpeg command
            rtmp_url = f"rtmp://a.rtmp.youtube.com/live2/{stream_key}"
            
            command = [
                'ffmpeg',
                '-re',
                '-stream_loop', '-1',
                '-i', video_path,
                '-c:v', 'copy',
                '-c:a', 'copy',
                '-f', 'flv',
                rtmp_url
            ]
            
            logging.info(f"Starting FFmpeg with command: {' '.join(command)}")

            # Run FFmpeg as a background process
            subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

            return jsonify({"message": f"Stream for '{filename}' has been started successfully!"}), 200

        except Exception as e:
            logging.error(f"An error occurred: {e}")
            return jsonify({"error": f"An internal server error occurred: {e}"}), 500

    else:
        return jsonify({"error": "File type not allowed. Please use MP4, MOV, MKV, or AVI."}), 400

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
