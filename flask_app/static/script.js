document.addEventListener("DOMContentLoaded", function () {
    fetchAnswers(); // Load saved answers on page load
});

function evaluateAnswer(questionId) {
    let answer = document.getElementById(questionId).value;

    fetch("http://127.0.0.1:5000/generate_feedback", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ question_id: questionId, answer: answer })
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById("feedback-" + questionId).innerText = data[questionId] || "Error processing feedback.";
    })
    .catch(error => console.error("Error:", error));
}

function saveAllAnswers() {
    let answers = {
        q1: document.getElementById("q1").value,
        q2: document.getElementById("q2").value
    };

    fetch("http://127.0.0.1:5000/save_answers", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify(answers)
    })
    .then(response => response.json())
    .then(data => {
        document.getElementById("status").innerText = data.message;
    })
    .catch(error => console.error("Error:", error));
}

function fetchAnswers() {
    fetch("http://127.0.0.1:5000/get_answers")
    .then(response => response.json())
    .then(data => {
        document.getElementById("q1").value = data.q1 || "";
        document.getElementById("q2").value = data.q2 || "";
    })
    .catch(error => console.error("Error:", error));
}

function sendChatMessage() {
    let message = document.getElementById("chat-input").value;
    if (!message.trim()) return;
    
    fetch("http://127.0.0.1:5000/chat", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ message: message })
    })
    .then(response => response.json())
    .then(data => {
        let responseText = data.response;
        let targets = data.target; // This can be an array of targets

        // Ensure targets is always an array
        if (!Array.isArray(targets)) {
            targets = [targets];
        }

        // Display response in multiple locations
        targets.forEach(target => {
            if (target.startsWith("feedback")) {
                let feedbackElement = document.getElementById(target);
                if (feedbackElement) {
                    feedbackElement.innerText = responseText;
                }
            } else if (target === "chat") {
                let chatBox = document.getElementById("chat-box");
                let newMessage = document.createElement("div");
                newMessage.innerHTML = `<strong>You:</strong> ${message} <br> <strong>Agent:</strong> ${responseText}`;
                chatBox.appendChild(newMessage);
            }
        });

        document.getElementById("chat-input").value = ""; // Clear input field
    })
    .catch(error => console.error("Error:", error));
}