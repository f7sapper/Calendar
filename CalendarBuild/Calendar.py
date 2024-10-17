from flask import Flask, render_template, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import pytz
import requests
import requests_cache
import pandas as pd
from retry_requests import retry
import openmeteo_requests  # To interact with Open-Meteo's API
from openmeteo_sdk.Variable import Variable  # To use Open-Meteo's Variable class


app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///calendar.db'
db = SQLAlchemy(app)

@app.route('/')
def home():
    return render_template('Calendar.html')

# Setup requests cache and retry logic
cache_session = requests_cache.CachedSession('.cache', expire_after=3600)
retry_session = retry(cache_session, retries=5, backoff_factor=0.2)

# Appointment Model
class Appointment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(100))
    start_time = db.Column(db.DateTime)
    end_time = db.Column(db.DateTime)
    description = db.Column(db.String(200))
    color = db.Column(db.String(20))  

# User Preferences Model (for weather city and favorite sports teams)
class UserPreference(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    favorite_city = db.Column(db.String(100))
   

# Global list to store appointments
appointments = []

# Fetch all appointments
@app.route('/appointments', methods=['GET'])
def get_appointments():
    return jsonify(appointments)

# Add a new appointment
@app.route('/appointments', methods=['POST'])
def add_appointment():
    try:
        new_appointment = request.json

        # Validate the incoming data
        if not new_appointment.get('title') or not new_appointment.get('start'):
            return jsonify({"error": "Title and start date are required"}), 400

        # Assign an ID to the new appointment
        new_appointment['id'] = len(appointments) + 1  # Simplistic ID assignment

        # Append the new appointment to the list
        appointments.append(new_appointment)

        # Return the newly created appointment with a 201 status
        return jsonify(new_appointment), 201

    except Exception as e:
        print(f"Error adding appointment: {e}")
        return jsonify({"error": "Failed to add event"}), 500

# Delete an appointment
@app.route('/appointments/<int:appointment_id>', methods=['DELETE'])
def delete_appointment(appointment_id):
    global appointments
    appointments = [appt for appt in appointments if appt['id'] != appointment_id]
    return '', 204



# Get current time in all US time zones
@app.route('/timezones', methods=['GET'])
def get_us_timezones():
    # Get current UTC time
    now_utc = datetime.utcnow()

    # Calculate the current time for each time zone by adjusting UTC and format to 12-hour
    timezones = {
        'Eastern': (now_utc - timedelta(hours=4)).strftime('%I:%M %p'),  # UTC - 4 for EDT
        'Central': (now_utc - timedelta(hours=5)).strftime('%I:%M %p'),  # UTC - 5 for CDT
        'Mountain': (now_utc - timedelta(hours=6)).strftime('%I:%M %p'), # UTC - 6 for MDT
        'Pacific': (now_utc - timedelta(hours=7)).strftime('%I:%M %p')   # UTC - 7 for PDT
    }
    return jsonify(timezones)
    
# Get weather information (Open-Meteo API)
@app.route('/weather', methods=['GET'])
@app.route('/weather/', methods=['GET'])
def get_weather():
    try:
        # Open-Meteo API URL and parameters
        url = "https://api.open-meteo.com/v1/forecast"
        params = {
            "latitude": 35.84,  # Example latitude
            "longitude": -86.39,  # Example longitude
            "current_weather": True,
            "daily": [
                "temperature_2m_max", "temperature_2m_min", "precipitation_sum", 
                "precipitation_probability_max", "windspeed_10m_max", "weather_code", 
                "winddirection_10m_dominant"
            ],
            "timezone": "auto"
        }

        # Make the request to Open-Meteo API
        response = retry_session.get(url, params=params)

        # Debugging: Print the URL, status code, and response content
        print(f"API Request URL: {response.url}")
        print(f"Response Status Code: {response.status_code}")
        print(f"Response Content: {response.text[:200]}...")  # Print a snippet of the content for debugging

        if response.status_code == 200:
            weather_data = response.json()  # Parse the weather data as JSON

            # Extract current weather
            current_weather = weather_data.get('current_weather', {})
            temperature = current_weather.get('temperature')
            wind_speed = current_weather.get('windspeed')
            wind_direction = current_weather.get('winddirection')  # Add wind direction

            # Extract daily weather data
            daily_data = weather_data.get('daily', {})
            
            # Combine current weather and daily forecast data into a single JSON response
            combined_data = {
                "temperature": temperature,  # Assuming this is in Celsius
                "wind_speed": wind_speed,  # Assuming this is in km/h
                "wind_direction": wind_direction,  # Include wind direction
                "daily": {
                    "temperature_max": daily_data.get('temperature_2m_max', []),
                    "temperature_min": daily_data.get('temperature_2m_min', []),
                    "precipitation_sum": daily_data.get('precipitation_sum', []),
                    "precipitation_probability": daily_data.get('precipitation_probability_max', []),
                    "windspeed_max": daily_data.get('windspeed_10m_max', []),
                    "wind_direction": daily_data.get('winddirection_10m_dominant', []),  # Include wind direction for daily
                    "weather_code": daily_data.get('weather_code', []),
                    "time": daily_data.get('time', [])
                }
            }

            # Debugging: Print the combined data to ensure it's structured correctly
            print(f"Combined Weather Data: {combined_data}")

            # Return the combined weather data as JSON
            return jsonify(combined_data)
        else:
            # Log detailed error response for debugging
            print(f"Error fetching weather data: {response.status_code}, {response.text}")
            return jsonify({"error": "Failed to fetch weather data"}), response.status_code

    except Exception as e:
        # Handle any errors that may occur
        print(f"Exception occurred: {e}")
        return jsonify({"error": str(e)}), 500


if __name__ == '__main__':
    with app.app_context():
        db.create_all()  # Ensures the database is created within the app context
    app.run(host='0.0.0.0', port=8000, debug=True)
