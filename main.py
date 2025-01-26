import uvicorn
import os
import sys

# Add the app directory to the Python path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

if __name__ == "__main__":
    # Run the FastAPI application using uvicorn
    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",  # Allows external access
        port=8523,
        reload=True  # Enable auto-reload during development
    )