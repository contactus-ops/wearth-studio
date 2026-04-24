from flask import Flask, send_file, request, jsonify
import os
import requests

app = Flask(__name__)

@app.route('/')
def index():
    return send_file('index.html')

@app.route('/manifest.json')
def manifest():
    return send_file('manifest.json')

@app.route('/sw.js')
def sw():
    return send_file('sw.js')

@app.route('/api/captions', methods=['POST'])
def captions():
    data = request.json
    mood = data.get('mood', '')
    
    resp = requests.post(
        'https://api.anthropic.com/v1/messages',
        headers={
            'Content-Type': 'application/json',
            'x-api-key': os.environ.get('ANTHROPIC_API_KEY', ''),
            'anthropic-version': '2023-06-01'
        },
        json={
            'model': 'claude-sonnet-4-20250514',
            'max_tokens': 1200,
            'messages': [{
                'role': 'user',
                'content': f'Write 3 Instagram captions for WEARTH — Indian activewear made from plant-based eucalyptus. Founded by Shai in India. Real human voice, never AI-sounding. No TENCEL or lyocell. No polyester positive framing. Lowercase tone, short punchy lines, no exclamation marks. Mood: {mood}.\n\nEnd each with: #WearthActive #PlantBasedActivewear #IndianActivewear #NoPolyester #EucalyptusActivewear #MoveWithIntention\n\nReturn ONLY a JSON array of 3 strings. No markdown. Start with ['
            }]
        }
    )
    return jsonify(resp.json())

@app.route('/<path:path>')
def static_files(path):
    return send_file(path)

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port)
