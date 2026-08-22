from flask import Flask
from config import db

app = Flask(__name__)

@app.route("/")
def home():
    return "DayFlow HRMS is running!"

if __name__ == "__main__":
    app.run(debug=True)