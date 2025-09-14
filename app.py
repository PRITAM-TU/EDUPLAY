from flask import Flask, jsonify, request, send_file, render_template, session, redirect, url_for
from flask_cors import CORS
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from flask_pymongo import PyMongo
from werkzeug.security import generate_password_hash, check_password_hash
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
import base64
import json
import random
import uuid
from datetime import datetime, timedelta
import os
from bson.objectid import ObjectId

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'  # Change this in production

# MongoDB configuration
app.config["MONGO_URI"] = "mongodb+srv://pritamtung03_db_user:WLIFVuRwEev7APoP@cluster0.4ysopge.mongodb.net/Study_game"
mongo = PyMongo(app)

# Flask-Login configuration
login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# User class for Flask-Login
class User(UserMixin):
    def __init__(self, user_data):
        self.id = str(user_data['_id'])
        self.username = user_data['username']
        self.email = user_data.get('email', '')
        self.user_data = user_data

@login_manager.user_loader
def load_user(user_id):
    user_data = mongo.db.users.find_one({'_id': ObjectId(user_id)})
    if user_data:
        return User(user_data)
    return None

# Sample question bank
def create_sample_questions():
    questions = []
    for i in range(1, 101):
        subject = 'Math' if i <= 40 else 'Science' if i <= 70 else 'History'
        
        if subject == 'Math':
            topic = 'Algebra' if i <= 20 else 'Geometry'
        elif subject == 'Science':
            topic = 'Physics' if i <= 55 else 'Chemistry'
        else:
            topic = 'World' if i <= 85 else 'US'
            
        difficulty = 'Easy' if i <= 30 else 'Medium' if i <= 70 else 'Hard'
        
        questions.append({
            'id': i,
            'subject': subject,
            'topic': topic,
            'difficulty': difficulty,
            'question': f'Sample question {i} - This is a {difficulty.lower()} {topic} question for {subject}',
            'options': ['A', 'B', 'C', 'D'],
            'answer': random.choice(['A', 'B', 'C', 'D'])
        })
    
    return pd.DataFrame(questions)

questions_df = create_sample_questions()
questions_df.to_csv('questions.csv', index=False)

# Authentication routes
@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        email = data.get('email')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Check if user already exists
        if mongo.db.users.find_one({'username': username}):
            return jsonify({'error': 'Username already exists'}), 409
        
        # Create new user
        hashed_password = generate_password_hash(password)
        user_id = mongo.db.users.insert_one({
            'username': username,
            'email': email,
            'password': hashed_password,
            'created_at': datetime.now()
        }).inserted_id
        
        # Create user progress document
        mongo.db.user_progress.insert_one({
            'user_id': user_id,
            'answered_questions': [],
            'study_sessions': [],
            'performance_by_topic': {},
            'created_at': datetime.now()
        })
        
        return jsonify({'message': 'User created successfully'}), 201
    
    return render_template('index.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        data = request.json
        username = data.get('username')
        password = data.get('password')
        
        if not username or not password:
            return jsonify({'error': 'Username and password are required'}), 400
        
        # Find user in database
        user_data = mongo.db.users.find_one({'username': username})
        if user_data and check_password_hash(user_data['password'], password):
            user = User(user_data)
            login_user(user)
            return jsonify({'message': 'Login successful'}), 200
        else:
            return jsonify({'error': 'Invalid username or password'}), 401
    
    return render_template('index.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return jsonify({'message': 'Logout successful'}), 200

@app.route('/')
def index():
    return render_template('index.html')

# API routes (updated to use MongoDB)
@app.route('/api/questions')
@login_required
def get_questions():
    subject = request.args.get('subject', 'All')
    topic = request.args.get('topic', 'All')
    difficulty = request.args.get('difficulty', 'All')
    limit = int(request.args.get('limit', 10))
    
    filtered_df = questions_df
    if subject != 'All':
        filtered_df = filtered_df[filtered_df['subject'] == subject]
    if topic != 'All':
        filtered_df = filtered_df[filtered_df['topic'] == topic]
    if difficulty != 'All':
        filtered_df = filtered_df[filtered_df['difficulty'] == difficulty]
        
    if len(filtered_df) > limit:
        filtered_df = filtered_df.sample(limit)
        
    return jsonify(filtered_df.to_dict('records'))

@app.route('/api/answer', methods=['POST'])
@login_required
def submit_answer():
    data = request.json
    question_id = data['question_id']
    user_answer = data['answer']
    
    question = questions_df[questions_df['id'] == question_id].iloc[0]
    is_correct = user_answer == question['answer']
    
    # Update progress in MongoDB
    user_progress = mongo.db.user_progress.find_one({'user_id': ObjectId(current_user.id)})
    
    if not user_progress:
        # Create progress document if it doesn't exist
        mongo.db.user_progress.insert_one({
            'user_id': ObjectId(current_user.id),
            'answered_questions': [],
            'study_sessions': [],
            'performance_by_topic': {}
        })
        user_progress = mongo.db.user_progress.find_one({'user_id': ObjectId(current_user.id)})
    
    # Update answered questions
    answered_questions = user_progress['answered_questions']
    answered_questions.append({
        'question_id': question_id,
        'user_answer': user_answer,
        'correct_answer': question['answer'],
        'is_correct': is_correct,
        'timestamp': datetime.now().isoformat(),
        'subject': question['subject'],
        'topic': question['topic'],
        'difficulty': question['difficulty']
    })
    
    # Update performance by topic
    performance_by_topic = user_progress['performance_by_topic']
    topic = question['topic']
    if topic not in performance_by_topic:
        performance_by_topic[topic] = {'correct': 0, 'total': 0}
    
    performance_by_topic[topic]['total'] += 1
    if is_correct:
        performance_by_topic[topic]['correct'] += 1
    
    # Save updated progress
    mongo.db.user_progress.update_one(
        {'user_id': ObjectId(current_user.id)},
        {'$set': {
            'answered_questions': answered_questions,
            'performance_by_topic': performance_by_topic
        }}
    )
    
    return jsonify({
        'is_correct': is_correct,
        'correct_answer': question['answer']
    })

@app.route('/api/study-session', methods=['POST'])
@login_required
def record_study_session():
    data = request.json
    
    user_progress = mongo.db.user_progress.find_one({'user_id': ObjectId(current_user.id)})
    study_sessions = user_progress['study_sessions']
    
    study_sessions.append({
        'subject': data['subject'],
        'topic': data['topic'],
        'duration': data['duration'],
        'date': datetime.now().isoformat()
    })
    
    mongo.db.user_progress.update_one(
        {'user_id': ObjectId(current_user.id)},
        {'$set': {'study_sessions': study_sessions}}
    )
    
    return jsonify({'status': 'success'})

@app.route('/api/performance')
@login_required
def get_performance():
    user_progress = mongo.db.user_progress.find_one({'user_id': ObjectId(current_user.id)})
    
    if not user_progress or 'answered_questions' not in user_progress:
        return jsonify({
            'overall_accuracy': 0, 
            'by_topic': {}, 
            'by_date': {},
            'answered_questions_count': 0
        })
    
    answered = user_progress['answered_questions']
    if not answered:
        return jsonify({
            'overall_accuracy': 0, 
            'by_topic': {}, 
            'by_date': {},
            'answered_questions_count': 0
        })
    
    correct_count = sum(1 for q in answered if q['is_correct'])
    overall_accuracy = correct_count / len(answered)
    
    # Performance by topic
    performance_by_topic = user_progress.get('performance_by_topic', {})
    by_topic = {}
    for topic, data in performance_by_topic.items():
        if data['total'] > 0:
            by_topic[topic] = data['correct'] / data['total']
    
    # Performance by date (last 7 days)
    by_date = {}
    today = datetime.now()
    for i in range(7):
        date = (today - timedelta(days=i)).strftime('%Y-%m-%d')
        day_questions = [q for q in answered if q['timestamp'].startswith(date)]
        if day_questions:
            correct = sum(1 for q in day_questions if q['is_correct'])
            by_date[date] = correct / len(day_questions)
    
    return jsonify({
        'overall_accuracy': overall_accuracy,
        'by_topic': by_topic,
        'by_date': by_date,
        'answered_questions_count': len(answered)
    })

@app.route('/api/performance-chart')
@login_required
def get_performance_chart():
    user_progress = mongo.db.user_progress.find_one({'user_id': ObjectId(current_user.id)})
    performance = user_progress.get('performance_by_topic', {}) if user_progress else {}
    
    if not performance:
        # Create a placeholder image if no data
        plt.figure(figsize=(10, 6))
        plt.text(0.5, 0.5, 'No data available yet.\nComplete some quizzes first.', 
                 horizontalalignment='center', verticalalignment='center', 
                 fontsize=16, transform=plt.gca().transAxes)
        plt.axis('off')
    else:
        topics = list(performance.keys())
        accuracy = [performance[t]['correct']/performance[t]['total'] if performance[t]['total'] > 0 else 0 
                    for t in topics]
        
        plt.figure(figsize=(10, 6))
        plt.barh(topics, accuracy)
        plt.xlabel('Accuracy')
        plt.title('Performance by Topic')
        plt.tight_layout()
    
    # Save plot to bytes
    img = io.BytesIO()
    plt.savefig(img, format='png')
    img.seek(0)
    plt.close()
    
    return send_file(img, mimetype='image/png')

@app.route('/api/recommendations')
@login_required
def get_recommendations():
    user_progress = mongo.db.user_progress.find_one({'user_id': ObjectId(current_user.id)})
    performance = user_progress.get('performance_by_topic', {}) if user_progress else {}
    
    if not performance:
        return jsonify({'recommendations': ['Start with basic questions in any subject']})
    
    # Calculate accuracy for each topic
    topic_accuracy = []
    for topic, data in performance.items():
        if data['total'] > 0:
            accuracy = data['correct'] / data['total']
            topic_accuracy.append((topic, accuracy))
    
    # Sort by accuracy (lowest first)
    topic_accuracy.sort(key=lambda x: x[1])
    
    recommendations = []
    for topic, accuracy in topic_accuracy[:3]:  # Top 3 weakest topics
        recommendations.append(f'Practice more {topic} questions (current accuracy: {accuracy:.0%})')
    
    if not recommendations:
        recommendations.append('Keep practicing! Try different difficulty levels.')
    
    return jsonify({'recommendations': recommendations})

@app.route('/api/study-sessions')
@login_required
def get_study_sessions():
    user_progress = mongo.db.user_progress.find_one({'user_id': ObjectId(current_user.id)})
    sessions = user_progress.get('study_sessions', []) if user_progress else []
    
    # Calculate total study time
    total_minutes = sum(session.get('duration', 0) for session in sessions)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    
    return jsonify({
        'sessions': sessions[-10:],  # Return only the last 10 sessions
        'total_study_time': f'{hours}h {minutes}m'
    })

@app.route('/api/user')
@login_required
def get_user_info():
    user_data = mongo.db.users.find_one({'_id': ObjectId(current_user.id)})
    if user_data:
        return jsonify({
            'username': user_data['username'],
            'email': user_data.get('email', '')
        })
    return jsonify({'error': 'User not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)