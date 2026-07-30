#!/bin/bash
echo "============================================"
echo " YWAM Tailoring Centre Management System"
echo "============================================"
echo

if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3 -m venv venv
fi

source venv/bin/activate

echo "Installing/checking requirements..."
pip install -r requirements.txt --quiet

echo
echo "Starting the application..."
echo "Open your browser at http://127.0.0.1:5000"
echo "Press CTRL+C to stop the server."
echo

python3 app.py
