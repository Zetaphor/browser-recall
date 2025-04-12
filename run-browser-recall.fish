#!/usr/bin/env fish

# Change to the script's directory
cd (dirname (status filename))

# Activate the virtual environment and run main.py silently
source ./venv/bin/activate
python main.py > /dev/null 2>&1 &

# Print a simple confirmation message
echo "Browser Recall started in background"