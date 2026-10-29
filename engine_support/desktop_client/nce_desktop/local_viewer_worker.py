"""Wait for Windows process-tree ownership before starting the original viewer."""

from pathlib import Path
import sys
import time

gate, script, port = sys.argv[1:]
deadline = time.monotonic() + 30
while not Path(gate).is_file():
    if time.monotonic() > deadline:
        raise SystemExit(2)
    time.sleep(0.05)

from streamlit.web import cli

# Preserve the original chart code while adapting its legacy image-size option
# to newer Streamlit releases. Older desktop runtimes keep their original API.
import inspect
import streamlit as st
if inspect.signature(st.image).parameters['width'].default == 'content':
    original_image = st.image
    def compatible_image(*args, **kwargs):
        old_width = kwargs.pop('use_column_width', None)
        if old_width in (True, 'always') and 'width' not in kwargs:
            kwargs['width'] = 'stretch'
        return original_image(*args, **kwargs)
    st.image = compatible_image

sys.argv = [
    "streamlit",
    "run",
    script,
    "--global.developmentMode=false",
    "--server.address=127.0.0.1",
    f"--server.port={port}",
    "--server.headless=true",
    "--browser.gatherUsageStats=false",
    "--server.fileWatcherType=none",
    "--client.toolbarMode=minimal",
]
raise SystemExit(cli.main())
