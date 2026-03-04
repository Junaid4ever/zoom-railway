from flask import Flask, render_template, jsonify, request
from flask_socketio import SocketIO, emit
import time
import threading
import json
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret!'
socketio = SocketIO(app, cors_allowed_origins="*")

# Store connected instances
instances = {}
commands = {}

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/instances')
def get_instances():
    # Clean up old instances (older than 30 seconds)
    current_time = time.time()
    to_delete = []
    for instance_id, data in instances.items():
        if current_time - data['lastSeen'] > 30:
            to_delete.append(instance_id)
    
    for instance_id in to_delete:
        del instances[instance_id]
    
    return jsonify(instances)

@app.route('/command/<instance_id>', methods=['POST'])
def send_command(instance_id):
    data = request.json
    if instance_id not in commands:
        commands[instance_id] = []
    commands[instance_id].append(data)
    
    # Emit to specific instance via socket
    socketio.emit(f'command_{instance_id}', data)
    
    return jsonify({'status': 'ok'})

@socketio.on('register')
def handle_register(data):
    instance_id = data['instanceId']
    instances[instance_id] = {
        'instanceId': instance_id,
        'currentUsers': data.get('currentUsers', 0),
        'maxUsers': data.get('maxUsers', 10),
        'lastSeen': time.time()
    }
    print(f"✅ Instance registered: {instance_id}")
    emit('registered', {'status': 'ok'})

@socketio.on('heartbeat')
def handle_heartbeat(data):
    instance_id = data['instanceId']
    if instance_id in instances:
        instances[instance_id]['currentUsers'] = data.get('currentUsers', 0)
        instances[instance_id]['lastSeen'] = time.time()
    print(f"💓 Heartbeat from {instance_id}")

@socketio.on('command_result')
def handle_command_result(data):
    instance_id = data['instanceId']
    print(f"📨 Command result from {instance_id}: {data}")

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
