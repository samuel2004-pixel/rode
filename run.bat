@echo off
echo ============================================
echo  YWAM Tailoring Centre Management System
echo ============================================
echo.

IF NOT EXIST venv (
    echo Creating virtual environment...
    python -m venv venv
)

call venv\Scripts\activate

echo Installing/checking requirements...
pip install -r requirements.txt --quiet

echo.
echo Starting the application...
echo Open your browser at http://127.0.0.1:5000
echo Press CTRL+C in this window to stop the server.
echo.

python app.py

pause
