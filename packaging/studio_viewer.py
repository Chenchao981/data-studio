"""Run the existing CP Cockpit with an owned lifetime; no account/server calls."""
import json
import sys
import time
from pathlib import Path

session,history_root,native_id=map(str,sys.argv[1:])
session=Path(session)
deadline=time.monotonic()+30
while not (session/'go').exists():
    if time.monotonic()>deadline:raise SystemExit(2)
    time.sleep(.05)
from nce_desktop.local_store import History
from nce_desktop.local_viewer import Viewers
viewers=Viewers(History(Path(history_root)),extra_paths=[Path(__file__).resolve().parent.parent/'viewer-packages'],runtime=sys.executable)
try:
    url=viewers.start(native_id)
    temp=session/'ready.pending'
    temp.write_text(json.dumps({'url':url}),encoding='utf8');temp.replace(session/'ready.json')
    while not (session/'stop').exists():time.sleep(.2)
finally:viewers.close()
