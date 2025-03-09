from flask import Flask, request, jsonify, render_template
from flask_cors import CORS

app = Flask(__name__)
CORS(app)  # Allow frontend requests

# Temporary storage (in-memory)
answers = {}

@app.route("/")
def index():
    return render_template("index.html")

@app.route('/save_answers', methods=['POST'])
def save_answers():
    """Save all answers at once."""
    data = request.json
    answers.update(data)  # Save all answers
    return jsonify({"message": "All answers saved successfully!"}), 200

@app.route('/get_answers', methods=['GET'])
def get_answers():
    """Retrieve saved answers."""
    return jsonify(answers), 200

@app.route('/generate_feedback', methods=['POST'])
def generate_feedback():
    """Generate feedback for a single question."""
    data = request.json
    question_id = data.get("question_id")
    text = data.get("answer", "")

    if not question_id or text.strip() == "":
        return jsonify({"feedback": "Please provide an answer before getting feedback."}), 200

    # Simple rule-based feedback
    if len(text.split()) < 10:
        feedback = "Try to elaborate more on your response."
    else:
        feedback = "Great response! You provided a well-thought-out answer."

    return jsonify({question_id: feedback}), 200

@app.route('/chat', methods=['POST'])
def chat():
    """Simple chatbot response logic. The response can go to the """
    data = request.json
    message = data.get("message", "").lower()

    if not message:
        return jsonify({"response": "Please enter a message.", "target": "chat"}), 200

    response = "That's interesting! Could you elaborate?"
    targets = ["chat"]  # Default to chat

    # Determine where to send the response
    if "hello" in message or "hi" in message:
        response = "Hello! How can I assist you today?" # Send only to Chat
    if "feedback" in message or "evaluate" in message:
        response = "Hello! How can I assist you today?"
        targets =["feedback-q2"] # Send only to Question 2 feedback
    if "technology" in message:
        response = "Technology is evolving rapidly! What specific aspect interests you?"
        targets.append("feedback-q1")  # Also send to Question 1 feedback
    if "ai" in message:
        response = "AI is transforming many industries. Do you think it will be beneficial?"
        targets.append("feedback-q2")  # Also send to Question 2 feedback

    return jsonify({"response": response, "target": targets}), 200

if __name__ == '__main__':
    # app.run(host='0.0.0.0', port=5000, debug=True)
    app.run(debug=True)
