# ### FINAL app.py with Embedded Credentials and Heartbeat ###
import os
import secrets
import threading
import docker
from urllib.parse import quote
from flask import Flask, request, jsonify
from datetime import datetime, timezone, timedelta

# Initialize Flask app
app = Flask(__name__)

# Initialize Docker client from environment
client = docker.from_env()

# A thread-safe dictionary to track containers and their last activity
managed_containers = {}

# Get required environment variables
HOST_IP = os.environ.get('HOST_IP')
HOST_PROFILES_PATH = os.environ.get('HOST_PROFILES_PATH')
if not HOST_IP or not HOST_PROFILES_PATH:
    raise ValueError("HOST_IP and HOST_PROFILES_PATH must be set.")

# --- INACTIVITY AND LIFETIME CONFIGURATION ---
SESSION_INACTIVITY_TIMEOUT = timedelta(minutes=30)

# --- FIXED APPLICATION CONFIGURATION ---
FIXED_GPT_URL = "https://chatgpt.com/g/g-Yd5GqNk3k-cook"
CHROME_FLAGS_TEMPLATE = "--app={start_url} --no-sandbox --test-type"

# --- Helper Functions ---
def generate_password(length=16): return secrets.token_urlsafe(length)
def find_free_port():
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('', 0)); return s.getsockname()[1]

def session_watchdog():
    threading.Timer(60, session_watchdog).start()
    now = datetime.now(timezone.utc)
    app.logger.info(f"Running session watchdog on {len(managed_containers)} containers...")
    for container_id, session_data in list(managed_containers.items()):
        if now - session_data.get('last_active', now) > SESSION_INACTIVITY_TIMEOUT:
            app.logger.warning(f"Container {container_id} for user {session_data['email']} is inactive. Stopping.")
            try: client.containers.get(container_id).stop(timeout=30)
            except docker.errors.NotFound: managed_containers.pop(container_id, None)

def cleanup_stopped_containers():
    threading.Timer(65, cleanup_stopped_containers).start()
    for container_id in list(managed_containers.keys()):
        try:
            container = client.containers.get(container_id)
            if container.status == 'exited':
                email = managed_containers.pop(container_id, {}).get('email', 'N/A')
                app.logger.info(f"Container {container_id} ({email}) was stopped. Removing.")
                container.remove(v=True)
        except docker.errors.NotFound:
            managed_containers.pop(container_id, None)

# --- API Endpoints ---
@app.route('/launch', methods=['POST'])
def launch_kasm_container():
    data = request.get_json()
    if not data or 'email' not in data:
        return jsonify({"error": "email not provided"}), 400

    email = data['email']
    name = data.get('name', '')
    key = data.get('key', 'skey@dc636923215643')

    # Find if a container already exists for this user
    for container_id, session_data in managed_containers.items():
        if session_data['email'] == email:
            try:
                container = client.containers.get(container_id)
                if container.status == 'running':
                    # Update last active time for the existing session
                    managed_containers[container_id]['last_active'] = datetime.now(timezone.utc)

                    # Get existing port and password to reconstruct the URL
                    ports = container.attrs['NetworkSettings']['Ports']
                    host_port = ports.get('3001/tcp', [{'HostPort': None}])[0]['HostPort']
                    if not host_port:
                        return jsonify({"error": "Existing container found but port could not be determined"}), 500
                    
                    password = container.attrs['Config']['Env']
                    password = next((p.split('=')[1] for p in password if p.startswith('PASSWORD=')), None)
                    if not password:
                        return jsonify({"error": "Existing container found but password could not be determined"}), 500

                    encoded_user = quote(email)
                    encoded_pass = quote(password)
                    access_url = f"https://{encoded_user}:{encoded_pass}@{HOST_IP}:{host_port}"

                    return jsonify({
                        "message": "User already has an active session. Returning existing session details.",
                        "url": access_url,
                        "container_id": container.id
                    }), 200
            except docker.errors.NotFound:
                # The container was removed but the dictionary wasn't updated yet.
                managed_containers.pop(container_id, None)
                continue  # Continue to launch a new container

    # If no existing container is found, proceed with launching a new one
    start_url = f"{FIXED_GPT_URL}?email={quote(email)}&name={quote(name)}&key={quote(key)}"
    chrome_flags = CHROME_FLAGS_TEMPLATE.format(start_url=start_url)
    
    title = 'Cloud GPT'
    password = generate_password()
    host_port = find_free_port()
    host_profile_path = os.path.join(HOST_PROFILES_PATH, email)
    custom_script_path = os.path.join(os.getcwd(), 'scripts', 'custom-init.sh')

    container_config = {
        "image": "lscr.io/linuxserver/chromium:latest",
        "detach": True,
        "security_opt": ["seccomp=unconfined"],
        "ports": {f'3001/tcp': host_port},
        "environment": {
            "PUID": "1000", "PGID": "1000", "TZ": "Etc/UTC",
            "CUSTOM_USER": email, "PASSWORD": password,
            "CHROME_CLI": chrome_flags,
            "TITLE": title,
            "NO_DECOR": "true"
        },
        "volumes": {
            host_profile_path: {"bind": "/config", "mode": "rw"},
            custom_script_path: {"bind": "/custom-cont-init.d/custom-init.sh", "mode": "ro"}
        },
        "shm_size": "2gb"
    }

    try:
        container = client.containers.run(**container_config)
        managed_containers[container.id] = {
            'email': email,
            'last_active': datetime.now(timezone.utc)
        }
        
        # --- Create the login URL with embedded credentials as requested ---
        encoded_user = quote(email)
        encoded_pass = quote(password)
        access_url = f"https://{encoded_user}:{encoded_pass}@{HOST_IP}:{host_port}"
        
        return jsonify({
            "message": "Chromium (Selkies) container launched successfully.",
            "url": access_url,
            "container_id": container.id
        }), 201
    except Exception as e:
        return jsonify({"error": f"Failed to launch container: {e}"}), 500

@app.route('/heartbeat', methods=['POST'])
def heartbeat():
    data = request.get_json()
    container_id = data.get('container_id')
    if container_id and container_id in managed_containers:
        managed_containers[container_id]['last_active'] = datetime.now(timezone.utc)
        app.logger.info(f"Received heartbeat for container {container_id}.")
        return jsonify({"status": "ok"}), 200
    return jsonify({"status": "not found"}), 404

@app.route('/list', methods=['GET'])
def list_containers():
    active_sessions = []
    for container_id, session_data in list(managed_containers.items()):
        try:
            container = client.containers.get(container_id)
            active_sessions.append({ "container_id": container.id, "status": container.status, "user_email": session_data.get('email', 'N/A') })
        except docker.errors.NotFound: managed_containers.pop(container_id, None)
    return jsonify(active_sessions)

@app.route('/remove', methods=['POST'])
def remove_container():
    data = request.get_json()
    container_id_to_remove = data.get('container_id')
    email_to_remove = data.get('email')
    if not container_id_to_remove and not email_to_remove: return jsonify({"error": "Either 'container_id' or 'email' must be provided"}), 400
    if email_to_remove:
        container_id_to_remove = next((cid for cid, sdata in managed_containers.items() if sdata.get('email') == email_to_remove), None)
        if not container_id_to_remove: return jsonify({"error": f"No active container found for email '{email_to_remove}'"}), 404
    if container_id_to_remove not in managed_containers: return jsonify({"error": f"Container ID '{container_id_to_remove}' not managed by this app"}), 404
    try:
        client.containers.get(container_id_to_remove).stop(timeout=30)
        return jsonify({"message": f"Container {container_id_to_remove} stopped successfully."})
    except docker.errors.NotFound:
        managed_containers.pop(container_id_to_remove, None)
        return jsonify({"message": "Container was already removed."}), 200
    except Exception as e: return jsonify({"error": f"An error occurred: {e}"}), 500

if __name__ == '__main__':
    session_watchdog()
    cleanup_stopped_containers()
    app.run(host='0.0.0.0', port=5000)
