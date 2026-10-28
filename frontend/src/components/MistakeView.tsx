
import { useEffect, useState } from 'react';

interface Mistake {
  id: string;
  question: string;
  correct_answer: string;
  wrong_answer: string;
  error_reason: string;
  knowledge_points: string;
  status: string;
  created_at: string | null;
}

const API_BASE = 'http://127.0.0.1:8000/api/v1';

function MistakeView() {
  const [mistakes, setMistakes] = useState<Mistake[]>([]);
  const [question, setQuestion] = useState('');
  const [correctAnswer, setCorrectAnswer] = useState('');
  const [wrongAnswer, setWrongAnswer] = useState('');
  const [errorReason, setErrorReason] = useState('');
  const [knowledgePoints, setKnowledgePoints] = useState('');
  const [loading, setLoading] = useState(false);
  const [message, setMessage] = useState('');

  const userId = JSON.parse(
    localStorage.getItem('currentUser') ||
      '{"id":"u_zhangsan"}'
  ).id || 'u_zhangsan';

  const loadMistakes = async () => {
    try {
      const response = await fetch(
        `${API_BASE}/mistakes?user_id=${encodeURIComponent(userId)}`
      );

      if (!response.ok) {
        throw new Error('获取错题列表失败');
      }

      setMistakes(await response.json());
    } catch {
      setMessage('无法连接后端，请确认后端服务正在运行。');
    }
  };

  useEffect(() => {
    void loadMistakes();
  }, [userId]);

  const handleReview = async (mistakeId: string) => {
  try {
    const response = await fetch(
      `${API_BASE}/mistakes/${encodeURIComponent(mistakeId)}/status?user_id=${encodeURIComponent(userId)}`,
      {
        method: 'PATCH',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ status: 'reviewed' }),
      }
    );

    if (!response.ok) {
      throw new Error('更新复习状态失败');
    }

    setMessage('复习状态更新成功');
    await loadMistakes();
  } catch {
    setMessage('复习状态更新失败，请检查后端服务');
  }
};

const handleEdit = async (item: Mistake) => {
  const updatedQuestion = window.prompt('修改题目内容：', item.question);
  if (updatedQuestion === null) return;

  if (!updatedQuestion.trim()) {
    setMessage('题目内容不能为空。');
    return;
  }

  const correctAnswer = window.prompt('修改正确答案：', item.correct_answer);
  if (correctAnswer === null) return;

  const wrongAnswer = window.prompt('修改错误答案：', item.wrong_answer);
  if (wrongAnswer === null) return;

  const errorReason = window.prompt('修改错误原因：', item.error_reason);
  if (errorReason === null) return;

  const knowledgePoints = window.prompt('修改关联知识点：', item.knowledge_points);
  if (knowledgePoints === null) return;

  try {
    const response = await fetch(
      `${API_BASE}/mistakes/${encodeURIComponent(item.id)}?user_id=${encodeURIComponent(userId)}`,
      {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          question: updatedQuestion.trim(),
          correct_answer: correctAnswer,
          wrong_answer: wrongAnswer,
          error_reason: errorReason,
          knowledge_points: knowledgePoints,
        }),
      }
    );

    if (!response.ok) {
      throw new Error('编辑失败');
    }

    setMessage('错题修改成功！');
    await loadMistakes();
  } catch {
    setMessage('编辑失败，请检查后端服务。');
  }
};

const handleDelete = async (item: Mistake) => {
  const confirmed = window.confirm(
    `确定要删除这道错题吗？\n\n${item.question}`
  );

  if (!confirmed) return;

  try {
    const response = await fetch(
      `${API_BASE}/mistakes/${encodeURIComponent(item.id)}?user_id=${encodeURIComponent(userId)}`,
      { method: 'DELETE' }
    );

    if (!response.ok) {
      throw new Error('删除失败');
    }

    setMessage('错题删除成功！');
    await loadMistakes();
  } catch {
    setMessage('删除失败，请检查后端服务。');
  }
};

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();

    if (!question.trim()) {
      setMessage('请先填写题目内容。');
      return;
    }

    setLoading(true);
    setMessage('');

    try {
      const response = await fetch(
        `${API_BASE}/mistakes?user_id=${encodeURIComponent(userId)}`,
        {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            question,
            correct_answer: correctAnswer,
            wrong_answer: wrongAnswer,
            error_reason: errorReason,
            knowledge_points: knowledgePoints,
          }),
        }
      );

      if (!response.ok) {
        throw new Error('添加失败');
      }

      setQuestion('');
      setCorrectAnswer('');
      setWrongAnswer('');
      setErrorReason('');
      setKnowledgePoints('');
      setMessage('错题添加成功！');

      await loadMistakes();
    } catch {
      setMessage('添加失败，请检查后端服务和网络连接。');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ maxWidth: 900, margin: '0 auto' }}>
      <h1 className="page-title">错题管理</h1>
      <p>记录错题、分析错误原因，逐步建立自己的薄弱知识点库。</p>

      <form
        onSubmit={handleSubmit}
        style={{
          display: 'grid',
          gap: 12,
          padding: 20,
          marginBottom: 24,
          border: '1px solid #e5e7eb',
          borderRadius: 12,
        }}
      >
        <h2>添加错题</h2>

        <label>
          题目内容 *
          <textarea
            required
            value={question}
            onChange={(e) => setQuestion(e.target.value)}
            placeholder="输入题目内容"
            rows={3}
            style={{ width: '100%', padding: 10, boxSizing: 'border-box' }}
          />
        </label>

        <label>
          正确答案
          <textarea
            value={correctAnswer}
            onChange={(e) => setCorrectAnswer(e.target.value)}
            placeholder="输入正确答案"
            rows={2}
            style={{ width: '100%', padding: 10, boxSizing: 'border-box' }}
          />
        </label>

        <label>
          我的错误答案
          <textarea
            value={wrongAnswer}
            onChange={(e) => setWrongAnswer(e.target.value)}
            placeholder="输入当时的错误答案"
            rows={2}
            style={{ width: '100%', padding: 10, boxSizing: 'border-box' }}
          />
        </label>

        <label>
          错误原因
          <textarea
            value={errorReason}
            onChange={(e) => setErrorReason(e.target.value)}
            placeholder="例如：公式记错、审题不清、计算失误"
            rows={2}
            style={{ width: '100%', padding: 10, boxSizing: 'border-box' }}
          />
        </label>

        <label>
          关联知识点
          <input
            value={knowledgePoints}
            onChange={(e) => setKnowledgePoints(e.target.value)}
            placeholder="例如：导数的基本公式"
            style={{ width: '100%', padding: 10, boxSizing: 'border-box' }}
          />
        </label>

        <button type="submit" disabled={loading}>
          {loading ? '正在保存...' : '保存错题'}
        </button>

        {message && <p role="status">{message}</p>}
      </form>

      <h2>我的错题（{mistakes.length}）</h2>

      {mistakes.length === 0 ? (
        <p>暂时没有错题，添加一道试试吧。</p>
      ) : (
        <div style={{ display: 'grid', gap: 16 }}>
          {mistakes.map((item) => (
            <article
              key={item.id}
              style={{
                padding: 18,
                border: '1px solid #e5e7eb',
                borderRadius: 12,
              }}
            >
              <h3>{item.question}</h3>
              <p><strong>正确答案：</strong>{item.correct_answer || '未填写'}</p>
              <p><strong>错误答案：</strong>{item.wrong_answer || '未填写'}</p>
              <p><strong>错误原因：</strong>{item.error_reason || '未填写'}</p>
              <p><strong>知识点：</strong>{item.knowledge_points || '未填写'}</p>
              <p>
                <strong>状态：</strong>
                {item.status === 'unreviewed' ? '待复习' : '已复习'}
              </p>
              <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
  {item.status === 'unreviewed' && (
    <button
      type="button"
      onClick={() => void handleReview(item.id)}
    >
      标记为已复习
    </button>
  )}

  <button
    type="button"
    onClick={() => void handleEdit(item)}
  >
    编辑错题
  </button>

  <button
    type="button"
    onClick={() => void handleDelete(item)}
  >
    删除错题
  </button>
</div>
            </article>
          ))}
        </div>
      )}
    </div>
  );
}

export default MistakeView;
