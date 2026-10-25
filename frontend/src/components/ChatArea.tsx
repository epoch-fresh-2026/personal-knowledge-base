import { useState } from 'react';
import { askQuestion } from '../api';

export default function ChatArea() {
  const [question, setQuestion] = useState('');
  const [loading, setLoading] = useState(false);
  const [messages, setMessages] = useState<{ role: 'user' | 'ai'; text: string; sources?: any[] }[]>([]);

  const handleAsk = async () => {
    if (!question.trim() || loading) return;
    const userMsg = question;
    setMessages((prev) => [...prev, { role: 'user', text: userMsg }]);
    setQuestion('');
    setLoading(true);

    try {
      const res = await askQuestion(userMsg);
      setMessages((prev) => [...prev, { role: 'ai', text: res.answer, sources: res.sources }]);
    } catch (err) {
      console.error(err);
      setMessages((prev) => [...prev, { role: 'ai', text: '请求出错了，请检查后端。' }]);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="card chat-container">
      <h3>💬 对话与问答</h3>
      <div className="chat-messages">
        {messages.map((msg, i) => (
          <div key={i} className={`message ${msg.role}`}>
            <div className="bubble">
              <div style={{ whiteSpace: 'pre-wrap' }}>{msg.text}</div>
              {msg.sources && msg.sources.length > 0 && (
                <div className="sources-box">
                  <div className="sources-title">参考来源：</div>
                  {msg.sources.map((s, idx) => (
                    <div key={idx} className="source-item">[{idx + 1}] {s.content.slice(0, 60)}...</div>
                  ))}
                </div>
              )}
            </div>
          </div>
        ))}
        {loading && <div className="message ai"><div className="bubble" style={{ color: '#888' }}>正在思考中...</div></div>}
      </div>

      <div className="chat-input-area">
        <input className="chat-input" type="text" value={question} onChange={(e) => setQuestion(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && handleAsk()} placeholder="输入你的问题..." />
        <button className="btn-primary" onClick={handleAsk} disabled={loading}>{loading ? '思考中...' : '发送'}</button>
      </div>
    </div>
  );
}