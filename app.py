from flask import Flask, jsonify, request, send_file, render_template
from flask_cors import CORS
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import io
import base64
import json
import random
from datetime import datetime, timedelta
import os

app = Flask(__name__)
CORS(app)

# Ensure necessary directories exist
os.makedirs('templates', exist_ok=True)
os.makedirs('static', exist_ok=True)

# Sample question bank (in real app, this would be loaded from CSV)
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

# Save sample questions to CSV
questions_df.to_csv('questions.csv', index=False)

# User progress tracking
def load_user_progress():
    try:
        with open('user_progress.json', 'r') as f:
            return json.load(f)
    except:
        return {
            'answered_questions': [],
            'study_sessions': [],
            'performance_by_topic': {}
        }

def save_user_progress():
    with open('user_progress.json', 'w') as f:
        json.dump(user_progress, f)

user_progress = load_user_progress()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/questions')
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
def submit_answer():
    data = request.json
    question_id = data['question_id']
    user_answer = data['answer']
    
    question = questions_df[questions_df['id'] == question_id].iloc[0]
    is_correct = user_answer == question['answer']
    
    # Update progress
    user_progress['answered_questions'].append({
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
    topic = question['topic']
    if topic not in user_progress['performance_by_topic']:
        user_progress['performance_by_topic'][topic] = {'correct': 0, 'total': 0}
    
    user_progress['performance_by_topic'][topic]['total'] += 1
    if is_correct:
        user_progress['performance_by_topic'][topic]['correct'] += 1
    
    # Save progress
    save_user_progress()
    
    return jsonify({
        'is_correct': is_correct,
        'correct_answer': question['answer']
    })

@app.route('/api/study-session', methods=['POST'])
def record_study_session():
    data = request.json
    user_progress['study_sessions'].append({
        'subject': data['subject'],
        'topic': data['topic'],
        'duration': data['duration'],
        'date': datetime.now().isoformat()
    })
    
    save_user_progress()
    
    return jsonify({'status': 'success'})

@app.route('/api/performance')
def get_performance():
    # Calculate overall performance
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
    by_topic = {}
    for topic, data in user_progress['performance_by_topic'].items():
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
def get_performance_chart():
    # Create a performance chart using Matplotlib
    performance = user_progress['performance_by_topic']
    
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
def get_recommendations():
    # Simple recommendation: suggest topics with lowest performance
    performance = user_progress['performance_by_topic']
    
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
def get_study_sessions():
    sessions = user_progress.get('study_sessions', [])
    
    # Calculate total study time
    total_minutes = sum(session['duration'] for session in sessions)
    hours = total_minutes // 60
    minutes = total_minutes % 60
    
    return jsonify({
        'sessions': sessions[-10:],  # Return only the last 10 sessions
        'total_study_time': f'{hours}h {minutes}m'
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)