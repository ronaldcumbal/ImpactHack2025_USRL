document.addEventListener("DOMContentLoaded", function () {
    fetchAnswers(); // Load saved answers on page load
});

const colors = ["#1f77b4","#ff7f0e","#2ca02c","#d62728","#9467bd","#8c564b"];

// Helper: escape HTML to prevent injection issues
function escapeHtml(text) {
    return text.replace(/&/g, "&amp;")
                .replace(/</g, "&lt;")
                .replace(/>/g, "&gt;");
}
  
// This function takes the raw text, the list of feedback segments, and the overlay element
// It wraps each occurrence of the feedback segment with a <span> styled with a color.
function updateOverlayHighlighting(text, feedbackList, overlayElement) {
    // Start with an HTML-escaped version of the text
    let escapedText = escapeHtml(text);
    console.log("highlighting")
    
    feedbackList.forEach((feedback, index) => {
        console.log("feedback:", feedback)
        let color = colors[index % colors.length];
        // Create a global, case-insensitive regex for the feedback segment.
        const regex = new RegExp(feedback, "gi");
        // Replace all occurrences with a span that has a background color.
        escapedText = escapedText.replace(regex, match => `<span style="background-color: ${color};">${match}</span>`);
    });

    overlayElement.innerHTML = escapedText;
}
  

function evaluateAnswer(questionId) {
    let answer = document.getElementById(questionId).value;
    let context = document.getElementById("context").value; // Get context input
    let feedbackContainer = document.getElementById("feedback-" + questionId);
    let overlayElement = document.getElementById("highlighted-content-" + questionId);

    // Clear previous feedback
    feedbackContainer.innerHTML = "";

    fetch("http://127.0.0.1:5000/generate_feedback", {
        method: "POST",
        headers: {
            "Content-Type": "application/json"
        },
        body: JSON.stringify({ 
            question_id: questionId, 
            answer: answer, 
            context: context // Send context to the backend
        })
    })
    .then(response => response.json())
    .then(data => {
        let feedbackList = data[questionId] || ["Error processing feedback."];
        let highlightList = data[questionId+"_extracts"] || ["Error processing highlights."];
        
        // TESTING - Update the text overlay with highlighted feedback segments.
        // updateOverlayHighlighting(answer, feedbackList, overlayElement);

        feedbackList.forEach(feedbackText => {
            let feedbackElement = document.createElement("div");
            feedbackElement.classList.add("feedback-item");
            feedbackElement.innerText = feedbackText;
            feedbackElement.onclick = function () {
                fetch("http://127.0.0.1:5000/set_chat_id", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({
                        question_id: questionId,
                        feedback_text: feedbackText
                    })
                })
                .then(response => response.json())
                .then(data => {
                    // data is expected to be a list of objects with keys "role" and "content"
                    let chatBox = document.getElementById("chat-box");
                    
                    // Optionally, clear previous messages in chat-box
                    chatBox.innerHTML = "";

                    data.forEach(item => {
                        let messageDiv = document.createElement("div");

                        // Create bold role element
                        let roleElement = document.createElement("strong");
                        roleElement.innerText = item.role + ": ";
                        messageDiv.appendChild(roleElement);

                        // Add the message content
                        let contentText = document.createTextNode(item.content);
                        messageDiv.appendChild(contentText);

                        // Append the message div to chat-box
                        chatBox.appendChild(messageDiv);
                    });
                })
            };
            feedbackContainer.appendChild(feedbackElement);
        });
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
        // data is expected to be a list of objects with keys "role" and "content"
        let chatBox = document.getElementById("chat-box");
            
        // Optionally, clear previous messages in chat-box
        chatBox.innerHTML = "";

        data.forEach(item => {
            let messageDiv = document.createElement("div");

            // Create bold role element
            let roleElement = document.createElement("strong");
            roleElement.innerText = item.role + ": ";
            messageDiv.appendChild(roleElement);

            // Add the message content
            let contentText = document.createTextNode(item.content);
            messageDiv.appendChild(contentText);

            // Append the message div to chat-box
            chatBox.appendChild(messageDiv);
        });

        document.getElementById("chat-input").value = "";
    })
    .catch(error => console.error("Error:", error));
}
