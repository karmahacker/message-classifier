#!/bin/sh
# Run both classifier and TM agent
gunicorn -w 2 -b 0.0.0.0:8000 app:app &
gunicorn -w 1 -b 0.0.0.0:8001 tm_agent:app &
wait
