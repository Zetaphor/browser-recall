#!/usr/bin/env fish

# Change to the script's directory
cd (dirname (status filename))

# Activate the virtual environment and run main.py silently
source (dirname (status filename))/.venv/bin/activate.fish
python src/main.py > /dev/null 2>&1 &

# Print a simple confirmation message using the correct variable for the last PID
echo "Browser Recall started in background with PID $last_pid"