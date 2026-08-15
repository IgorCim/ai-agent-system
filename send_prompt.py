"""Send the geomagnetic EXE app prompt to the agent and show the full process."""
import sys, json, urllib.request, time

sys.stdout.reconfigure(encoding='utf-8', errors='replace')

BASE = 'http://127.0.0.1:5000'

# Create session
sid = json.loads(urllib.request.urlopen(
    urllib.request.Request(BASE + '/api/session', method='POST'), timeout=10).read())['session_id']
print(f'Session: {sid}', flush=True)

PROMPT = '''Create a NEW Windows EXE application for visualizing Earth's magnetic field from JSON data on Desktop in a new folder called geomag_exe_app (do NOT touch old folders: geomag_field_viz, geomag_visualizer, geomag_viz_app).

The app must work with this EXACT JSON format (handle nulls in datetime and ll):
{
  "datetime": ["2026-04-13T00:00:00.000Z", "2026-04-13T00:01:00.000Z", "2026-04-13T00:02:00.000Z", "2026-04-13T00:03:00.000Z", "2026-04-13T00:04:00.000Z", "2026-04-13T00:05:00.000Z", "2026-04-13T00:06:00.000Z", "2026-04-13T00:07:00.000Z", null, null, null, null, null, null, null, null],
  "ll": [55.75, 37.62],
  "Bx": [18500.5, 18502.3, 18505.1, 18508.0, 18510.2, 18507.8, 18503.4, 18500.0, null, null, null, null, null, null, null, null],
  "By": [4880.1, 4878.5, 4876.2, 4874.0, 4875.3, 4877.8, 4880.5, 4882.0, null, null, null, null, null, null, null, null],
  "Bz": [43690.8, 43688.2, 43685.5, 43683.0, 43685.4, 43688.0, 43691.5, 43693.0, null, null, null, null, null, null, null, null],
  "Btotal": [47850.2, 47845.0, 47840.0, 47835.0, 47840.1, 47845.5, 47850.0, 47852.0, null, null, null, null, null, null, null, null],
  "unit": "nT",
  "station": "TEST_STATION",
  "latitude": 55.75,
  "longitude": 37.62
}

Requirements:
1. It must be a DESKTOP application (NOT web) — use tkinter or PyQt for the GUI
2. Include a JSON file with the sample data above (handle nulls properly)
3. Show interactive plots of Bx, By, Bz, Btotal over time
4. Skip/discount null values in plots, don't crash
5. Include station info from the JSON (ll, latitude, longitude, station name)
6. Use matplotlib with dark theme, save plot to PNG file
7. Build it into a single .exe file using PyInstaller (onefile mode)
8. The .exe must work standalone (copy to USB and run on any Windows PC)
9. Put ALL project files in Desktop\\geomag_exe_app folder
10. Name the exe: GeomagViewer.exe
11. Test the app by running it (python app.py) to verify it saves a PNG
12. Then build the exe and verify the exe was created

CRITICAL: Use matplotlib with non-interactive backend. Save plots to files, never try to show windows.'''

data = json.dumps({'session_id': sid, 'message': PROMPT}).encode()
req = urllib.request.Request(BASE + '/api/chat', data=data, headers={'Content-Type': 'application/json'})

try:
    with urllib.request.urlopen(req, timeout=600) as r:
        for line_bytes in r:
            line = line_bytes.decode('utf-8', errors='replace').strip()
            if not line or not line.startswith('data: '):
                continue
            ev = json.loads(line[6:])
            t = ev.get('type', '')
            if t == 'tool_start':
                tool = ev.get('tool', {})
                action = tool.get('action', '?')
                params = str(tool.get('command') or tool.get('path') or tool.get('pattern') or '')[:100]
                sys.stdout.write(f'  [TOOL] {action}: {params}\n')
            elif t == 'tool_result':
                ok = ev.get('result', {}).get('success', False)
                if not ok:
                    err = str(ev.get('result', {}).get('stderr', '') or '')[:120]
                    sys.stdout.write(f'  [RESULT] FAIL: {err}\n')
                else:
                    stdout = str(ev.get('result', {}).get('stdout', '') or '')[:100]
                    sys.stdout.write(f'  [RESULT] OK: {stdout}\n')
            elif t == 'user_text':
                text = ev.get('content', '')[:200]
                sys.stdout.write(f'  [TEXT] {text}\n')
            elif t == 'error':
                sys.stdout.write(f'  [ERROR] {ev.get("content","")[:150]}\n')
            elif t == 'done':
                sys.stdout.write(f'  [DONE]\n')
            sys.stdout.flush()
except Exception as e:
    sys.stdout.write(f'[EXCEPTION] {e}\n')

sys.stdout.write('\nDone!\n')
