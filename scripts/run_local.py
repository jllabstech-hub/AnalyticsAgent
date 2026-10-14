"""Run the installed Streamlit ASGI app on IPv4 and IPv6 localhost."""
import argparse
import os

import streamlit as st
import uvicorn

from analytics_agent.config import PROJECT_ROOT


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8502)
    parser.add_argument('--demo', action='store_true', help='Lock execution to synthetic data without LLM calls.')
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error('--port must be between 1 and 65535')
    os.environ['APP_ENV'] = 'local'
    if args.demo:
        os.environ['PUBLIC_DEMO_ENABLED'] = 'true'
    # Streamlit's CLI binds a single socket for an explicit IPv4 address.
    # Uvicorn resolves localhost and opens both loopback listeners in one process.
    uvicorn.run(st.App(PROJECT_ROOT / 'app.py'), host='localhost', port=args.port, log_level='info')


if __name__ == '__main__':
    main()
