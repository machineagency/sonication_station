#mjpg_streamer -i "input_raspicam.so -rot 180" -o "output_http.so -w /home/pi/mjpg-streamer/mjpg-streamer-experimental/www/"

echo "Launching Video Feed."
IP_ADDR="$( hostname -I | head -n1 | awk '{print $1;}' )"
STREAM_URL="http://$IP_ADDR:8080/stream_simple.html"
echo "Stream will be live at: $STREAM_URL"

# https://stackoverflow.com/questions/59895/how-to-get-the-source-directory-of-a-bash-script-from-within-the-script-itself
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" >/dev/null 2>&1 && pwd )"

mjpg_streamer -i "input_raspicam.so -rot 180" -o "output_http.so -w $SCRIPT_DIR/web_video_feed/"

