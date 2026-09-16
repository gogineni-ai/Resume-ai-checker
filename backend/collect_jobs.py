"""Run once with --config sources.json, or continuously with --interval 86400."""
import argparse
import asyncio
import json
import signal
import threading
from pathlib import Path
from app.main import initialize_database
from app.services.collector import run_collection

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--config',required=True)
    parser.add_argument('--interval',type=int,default=0)
    args=parser.parse_args()
    if args.interval and args.interval < 3600: parser.error('Interval must be at least one hour')
    stop=threading.Event()
    for sig in (signal.SIGTERM,signal.SIGINT): signal.signal(sig,lambda *_:stop.set())
    initialize_database()
    while not stop.is_set():
        configs=json.loads(Path(args.config).read_text())['sources']
        print(json.dumps(asyncio.run(run_collection(configs))),flush=True)
        if not args.interval or stop.wait(args.interval): break

if __name__=='__main__': main()
