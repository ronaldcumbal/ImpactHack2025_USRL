document.addEventListener("DOMContentLoaded", function () {
    fetchAnswers(); // Load saved answers on page load
});

const colors = ["#F6BD60","#EDDEA4","#F5CAC3","#84A59D","#F28482", "#D8D4F2"];

function getColor(score) {
    if (score <= 0.5) {
      // Interpolate between red (255,0,0) and orange (255,165,0)
      let factor = score / 0.5; // Ranges from 0 to 1
      let r = 255; // Always 255
      let g = Math.floor(0 + factor * (165 - 0));
      return `rgb(${r}, ${g}, 0)`;
    } else {
      // Interpolate between orange (255,165,0) and green (0,255,0)
      let factor = (score - 0.5) / 0.5; // Ranges from 0 to 1
      let r = Math.floor(255 - factor * (255 - 0));
      let g = Math.floor(165 + factor * (255 - 165));
      return `rgb(${r}, ${g}, 0)`;
    }
  }

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
        escapedText = escapedText.replace(regex, match => `<span style="background-color: ${color}; alpha:0.7;">${match}</span>`);
    });

    overlayElement.innerHTML = escapedText;
}
  

// Will fix the progress bar to 1
function okayParagraph(questionId) {
    let progressBar = document.getElementById('progressBar-' + questionId);
    progressBar.style.width = '100%';
    progressBar.style.backgroundColor = getColor(1);
    let feedbackContainer = document.getElementById("feedback-" + questionId);
    feedbackContainer.innerHTML = "";
}

function evaluateAnswer(questionId) {
    let answer = document.getElementById(questionId).value;
    let context = document.getElementById("context").value; // Get context input
    let feedbackContainer = document.getElementById("feedback-" + questionId);
    let overlayElement = document.getElementById("highlighted-content-" + questionId);
    let loadingGif = document.getElementById("loading-" + questionId);
    
    // Clear previous feedback
    feedbackContainer.innerHTML = "";

    // Show loading gif while waiting for the response
    loadingGif.style.display = "inline-block";

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
        
        updateOverlayHighlighting(answer, highlightList, overlayElement);

        feedbackList.forEach((feedbackText, index) => {
            let color = colors[index % colors.length];
            let feedbackElement = document.createElement("div");
            feedbackElement.classList.add("feedback-item");
            feedbackElement.style.backgroundColor =  color;
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
        // Hide loading gif once feedback is received
        loadingGif.style.display = "none";
    })
    .catch(error => console.error("Error:", error));
    fetch('http://127.0.0.1:5000/get_paragraph_score', {
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
        // Expecting data like: { "score": 0.75 }
        const score = data.score;
        const progressBar = document.getElementById('progressBar-' + questionId);

        if (progressBar) { // Ensure the element exists
            // Get the actual width (computed styles)
            const currentWidth = parseFloat(window.getComputedStyle(progressBar).width);
            const parentWidth = parseFloat(window.getComputedStyle(progressBar.parentElement).width);
            
            // Convert to a 0-1 scale
            const currentScore = currentWidth / parentWidth;

            // Only update if the new score is higher
            if (score > currentScore) {
                progressBar.style.width = (score * 100) + '%';
                progressBar.style.backgroundColor = getColor(score);
            }
        }
    })
    .catch(error => {
        console.error("Error:", error);
        loadingGif.style.display = "none"; // Hide loading gif in case of error
    });
}

function saveAllAnswers() {
    fetch("/generate_docx", { method: "POST" })
        .then(function (response) {
            if (!response.ok) {
                throw new Error("Failed to generate document");
            }
            return response.blob();
        })
        .then(function (blob) {
            var url = window.URL.createObjectURL(blob);
            var a = document.createElement("a");
            a.href = url;
            a.download = "generated_document.docx"; // Set the filename
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            window.URL.revokeObjectURL(url);
        })
        .catch(function (error) {
            console.error("Error:", error);
        });
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
    let loadingGif = document.getElementById("chat-loading");

    let chatBox = document.getElementById("chat-box");
    // Show loading gif while waiting for the response
    loadingGif.style.display = "inline-block";
    
    // clean input instantly
    document.getElementById("chat-input").value = "";
    // add message to chatBox
    let messageDiv = document.createElement("div");

    // Create bold role element
    let roleElement = document.createElement("strong");
    roleElement.innerText = "You: ";
    messageDiv.appendChild(roleElement);

    // Add the message content
    let contentText = document.createTextNode(message);
    messageDiv.appendChild(contentText);

    // Append the message div to chat-box
    chatBox.appendChild(messageDiv);

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


        // Hide the loading gif once the response is received
        loadingGif.style.display = "none";
    })
    .catch(error => {
        console.error("Error:", error);
        // Hide the loading gif in case of error
        loadingGif.style.display = "none";
    });
}

document.addEventListener("DOMContentLoaded", function () {
    const textareas = document.querySelectorAll('textarea')
    textareas.forEach(textarea => {
        textarea.addEventListener("input", function () {
            // Reset the height so it shrinks if needed
            this.style.height = "auto";
            // Set the height to match the scroll height
            const newHeight = this.scrollHeight + "px";
            this.style.height = newHeight;


            // Get the corresponding highlighter overlay by ID
            const overlayId = "highlighted-content-" + this.id;
            const overlayElement = document.getElementById(overlayId);
            if (overlayElement) {
                overlayElement.style.height = newHeight;
                // Update the overlay's content.
                // Use escapeHtml to avoid injecting raw HTML (if needed).
                overlayElement.innerHTML = escapeHtml(this.value);
            }
            // updateOverlayHighlighting(this.value, [], overlayElement);
        });
    });
});
