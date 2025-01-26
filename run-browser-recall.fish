#!/usr/bin/env fish

# Activate the virtual environment and run main.py silently
vf activate general
python main.py > /dev/null 2>&1 &

# Print a simple confirmation message
echo "Browser Recall started in background"