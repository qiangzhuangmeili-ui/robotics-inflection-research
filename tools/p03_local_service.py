"""Run the existing local workbench without its browser-opening launcher."""
import sys
from http.server import ThreadingHTTPServer
from pathlib import Path
WORKBENCH=Path('D:/StockResearchLab/AKShare/workbench')
sys.path.insert(0,str(WORKBENCH))
import app
if __name__=='__main__':
    server=ThreadingHTTPServer(('127.0.0.1',8774),app.Handler)
    server.daemon_threads=True
    print('Existing workbench listening on 127.0.0.1:8774; no browser opened.',flush=True)
    try:server.serve_forever()
    finally:server.server_close()
