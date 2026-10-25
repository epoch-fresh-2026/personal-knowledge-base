import { useState, useEffect } from 'react';
import { getUserPublicDocs } from '../api';

export default function UserProfileView({ userId, onBack }: { userId: string, onBack: () => void }) {
  const [docs, setDocs] = useState<any[]>([]);

  useEffect(() => { getUserPublicDocs(userId).then(setDocs).catch(console.error); }, [userId]);

  return (
    <div>
      <button onClick={onBack} style={{ marginBottom: '15px', cursor: 'pointer', background: 'none', border: 'none', color: '#8B6EC1' }}>⬅ 返回广场</button>
      <h2 className="page-title">作者主页</h2>
      <div className="card">
        <h3>公开资料列表</h3>
        {docs.length === 0 && <p style={{ color: '#999' }}>该用户还没有公开资料。</p>}
        <ul style={{ listStyle: 'none', padding: 0 }}>
          {docs.map(d => <li key={d.id} style={{ padding: '10px', borderBottom: '1px solid #eee' }}>📄 {d.title}</li>)}
        </ul>
      </div>
    </div>
  );
}