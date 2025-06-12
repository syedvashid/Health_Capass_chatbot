import React, { useState, useRef, useEffect } from 'react';
import './App.css';
import formImage from './img.png';

function App() {
  const [step, setStep] = useState('form'); // 'form' or 'chatbot'
  const [formData, setFormData] = useState({
    name: '',
    age: '',
    gender: 'Male',
    department: 'Fever and Cold', // Default department
    language: 'English', // New field for language
  });
  const [input, setInput] = useState('');
  const [messages, setMessages] = useState([]);
  const [isLoading, setIsLoading] = useState(false);
  const [suggestedDepartment, setSuggestedDepartment] = useState(''); // State for suggested department
  const [showQuickActions, setShowQuickActions] = useState(true); // State for quick action buttons
  const messagesEndRef = useRef(null);
  const [chatHistoryId, setChatHistoryId] = useState(null); // New state to store chat_history_id
  const [lastQuestionId, setLastQuestionId] = useState(null); // New state to store last_question_id

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    if (step === 'chatbot') scrollToBottom();
  }, [messages, step]);

  // Initialize chatbot with welcome message when switching to chatbot
  useEffect(() => {
    if (step === 'chatbot' && messages.length === 0) {
      const welcomeMessage = {
        role: 'assistant',
        content: `Hey ${formData.name}! 👋 I'm here to help you with your health concerns. I can assist you with:\n\n🔍 Health Diagnosis - Analyze your symptoms\n📅 Appointment Suggestions - Recommend specialists\n📞 Appointment Booking - Help schedule visits\n\nHow can I help you today?`
      };
      setMessages([welcomeMessage]);
    }
  }, [step, formData.name]);

  const handleFormSubmit = () => {
    if (!formData.name || !formData.age || !formData.department || !formData.language) {
      alert('Please fill all the fields before proceeding.');
      return;
    }
    setStep('chatbot');
  };

  // Quick action handlers
  const handleQuickAction = (action) => {
    let quickMessage = '';
    switch (action) {
      case 'diagnosis':
        quickMessage = 'I need help with health diagnosis. Can you analyze my symptoms?';
        break;
      case 'appointment':
        quickMessage = 'I would like appointment suggestions based on my condition.';
        break;
      case 'booking':
        quickMessage = 'I want to book an appointment with a specialist.';
        break;
      default:
        return;
    }
    
    setInput(quickMessage);
    setShowQuickActions(false); // Hide quick actions after first use
    setLastQuestionId(null); // <<< ADD THIS LINE: Clear lastQuestionId on quick action

  };
const handleSubmit = async (e) => {
    e.preventDefault();
    if (!input.trim()) return;

    setShowQuickActions(false);

    const userMessage = { role: 'user', content: input };
    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setIsLoading(true);

    const messagesToSend = [...messages, userMessage];

    try {
      const response = await fetch('http://localhost:8000/chat', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          user_input: input,
          department: formData.department,
          conversation_history: messagesToSend,
          language: formData.language,
          name: formData.name,
          age: formData.age,
          gender: formData.gender,
          chat_history_id: chatHistoryId, // <<< ADD THIS LINE
          last_question_id: lastQuestionId // <<< ADD THIS LINE
        }),
      });

      const data = await response.json();
      let newMessages = [...messagesToSend];

      // --- CRITICAL FIX FOR FLOW MARKER ---
      const hasFlowMarker = messagesToSend.some(
        (msg) => msg.role === 'system' && msg.content.startsWith('selected_flow:')
      );

      if (!hasFlowMarker) {
          const lowerInput = input.trim().toLowerCase();
          if (lowerInput.includes("diagnosis")) {
              newMessages.push({ role: 'system', content: `selected_flow: diagnosis` });
          } else if (lowerInput.includes("appointment")) {
              newMessages.push({ role: 'system', content: `selected_flow: appointment` });
          }
      }
      // --- END CRITICAL FIX ---
      
      // Add the assistant's response to the new messages array
      newMessages.push({ role: 'assistant', content: data.response });

      // <<< ADD THESE LINES TO STORE IDs >>>
      if (data.chat_history_id) {
        setChatHistoryId(data.chat_history_id);
      }
      if (data.question_id) {
        setLastQuestionId(data.question_id);
      } else {
        // If no new question is returned, clear lastQuestionId
        // This is important so future *non-answer* inputs don't try to save an answer
        setLastQuestionId(null);
      }
      // <<< END ADDED LINES >>>

      setMessages(newMessages);

    } catch (error) {
      console.error('Error:', error);
      setMessages((prev) => [
        ...prev,
        { role: 'assistant', content: 'Sorry, I encountered an error. Please try again.' },
      ]);
    } finally {
      setIsLoading(false);
    }
  };
  const generateReport = async () => {
    if (messages.length === 0) {
      alert('Please have a conversation before generating a report.');
      return;
    }

    setIsLoading(true);
    try {
      // Filter out 'system' messages before sending to generate_report,
      // as generate_report doesn't need them in its prompt and might process them incorrectly.
      const conversationHistoryForReport = messages.filter(msg => msg.role !== 'system');

      const response = await fetch('http://localhost:8000/generate_report', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: formData.name,
          gender: formData.gender,
          age: formData.age,
          language: formData.language,
          conversation_history: conversationHistoryForReport, // Send filtered history
        }),
      });

      const blob = await response.blob();
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'medical_report.pdf';
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (error) {
      console.error('Report error:', error);
      alert('Failed to generate report');
    } finally {
      setIsLoading(false);
    }
  };

  const generateOfflineReport = async () => {
    if (!formData.name || !formData.age || !formData.department || !formData.language) {
      alert('Please fill all the fields before generating the offline report.');
      return;
    }

    const responses = [
      { questionId: 1, option: 'A' },
      { questionId: 2, option: 'C' },
      { questionId: 3, option: 'B' },
      { questionId: 4, option: 'D' },
      { questionId: 5, option: 'A' },
    ];

    setIsLoading(true);
    try {
      const response = await fetch('http://localhost:8000/generate_offline_report', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          name: formData.name,
          age: formData.age,
          gender: formData.gender,
          department: formData.department,
          language: formData.language,
          responses: responses,
        }),
      });

      if (!response.ok) {
        throw new Error('Failed to generate offline report.');
      }

      const data = await response.json();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'offline_report.json';
      document.body.appendChild(a);
      a.click();
      a.remove();
    } catch (error) {
      console.error('Offline Report Error:', error);
      alert('Failed to generate offline report.');
    } finally {
      setIsLoading(false);
    }
  };

  const suggestDepartment = async () => {
    if (messages.length === 0) {
      alert('Please have a conversation before suggesting a department.');
      return;
    }

    setIsLoading(true);
    try {
      // Filter out 'system' messages before sending to suggest_department
      const conversationHistoryForSuggestion = messages.filter(msg => msg.role !== 'system');

      const response = await fetch('http://localhost:8000/suggest_department', {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          conversation_history: conversationHistoryForSuggestion,
        }),
      });

      const data = await response.json();
      setSuggestedDepartment(data.department || 'General Medicine');
      alert(`Suggested Department: ${data.department || 'General Medicine'}`);
    } catch (error) {
      console.error('Error suggesting department:', error);
      alert('Failed to suggest department.');
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="app">
      <header className="header">
        <h1>Medical Chatbot</h1>
      </header>
      {step === 'form' ? (
        <div className="form-container">
          <img src={formImage} alt="Medical Illustration" className="form-image" />
          <div>
            <h2>Enter Your Details</h2>
            <form>
              <label>
                Name:
                <input
                  type="text"
                  value={formData.name}
                  onChange={(e) => setFormData({ ...formData, name: e.target.value })}
                />
              </label>
              <label>
                Age:
                <input
                  type="number"
                  value={formData.age}
                  onChange={(e) => setFormData({ ...formData, age: e.target.value })}
                />
              </label>
              <label>
                Gender:
                <select
                  value={formData.gender}
                  onChange={(e) => setFormData({ ...formData, gender: e.target.value })}
                >
                  <option value="Male">Male</option>
                  <option value="Female">Female</option>
                  <option value="Other">Other</option>
                </select>
              </label>
              <label>
                Problem:
                <input
                  type="text"
                  value={formData.department}
                  onChange={(e) => setFormData({ ...formData, department: e.target.value })}
                />
              </label>
              <label>
                Language:
                <select
                  value={formData.language}
                  onChange={(e) => setFormData({ ...formData, language: e.target.value })}
                >
                  <option value="English">English</option>
                  <option value="Hindi">हिंदी</option>
                  <option value="Telugu">తెలుగు</option>
                </select>
              </label>
              <div className="form-buttons">
                <button type="button" onClick={handleFormSubmit}>
                  Open Chatbot
                </button>
                <button type="button" onClick={generateOfflineReport}>
                  Offline Report
                </button>
              </div>
            </form>
          </div>
        </div>
      ) : (
        <div className="chat-container">
          <div className="chat-box">
            <div className="messages">
              {messages.map((msg, index) => (
                // Only render messages that are not of role 'system'
                msg.role !== 'system' && (
                  <div key={index} className={`message ${msg.role}`}>
                    {msg.content}
                  </div>
                )
              ))}
              
              {/* Quick Action Buttons */}
              {showQuickActions && (
                <div className="quick-actions">
                  <p className="quick-actions-title">Quick Actions:</p>
                  <div className="quick-actions-buttons">
                    <button 
                      className="quick-action-btn diagnosis-btn"
                      onClick={() => handleQuickAction('diagnosis')}
                    >
                      🔍 Health Diagnosis
                    </button>
                    <button 
                      className="quick-action-btn appointment-btn"
                      onClick={() => handleQuickAction('appointment')}
                    >
                      📅 Appointment Suggestion
                    </button>
                    <button 
                      className="quick-action-btn booking-btn"
                      onClick={() => handleQuickAction('booking')}
                    >
                      📞 Book Appointment
                    </button>
                  </div>
                </div>
              )}
              
              <div ref={messagesEndRef} />
              {isLoading && <div className="message assistant typing">Typing...</div>}
            </div>

            <form onSubmit={handleSubmit} className="input-area">
              <input
                type="text"
                value={input}
                onChange={(e) => setInput(e.target.value)}
                placeholder="Type your symptoms or choose a quick action above..."
                disabled={isLoading}
              />
              <button type="submit" disabled={isLoading}>
                Send
              </button>
            </form>

            <div className="report-container">
              <button
                onClick={generateReport}
                disabled={isLoading || messages.length === 0}
                className="report-btn"
              >
                Generate PDF Report
              </button>
              <button
                onClick={suggestDepartment}
                disabled={isLoading || messages.length === 0}
                className="report-btn"
              >
                Suggest Department
              </button>
            </div>

            {suggestedDepartment && (
              <div className="suggested-department">
                <p>Suggested Department: {suggestedDepartment}</p>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}

export default App;