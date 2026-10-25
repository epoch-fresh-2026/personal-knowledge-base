import { useState, useEffect } from 'react';
import { getSquareDocs, getSquareFolders, toggleFavDoc, toggleFavFolder } from '../api';

export default function SquareView({ onViewUser }: { onViewUser: (uid: string) => void }) {
  const [docs, setDocs] = useState<any[]>([]);
  const [folders, setFolders] = useState<any[]>([]);
  const [keyword, setKeyword] = useState('');

  useEffect(() => { loadData(''); }, []);

  const loadData = async (searchWord: string) => {
    setDocs(await getSquareDocs(searchWord));
    setFolders(await getSquareFolders());
  };

  const handleFavDoc = async (id: string) => {
    await toggleFavDoc(id);
    alert('收藏操作成功！去“我的收藏”查看');
  };

  const handleFavFolder = async (id: string) => {
    await toggleFavFolder(id);
    alert('收藏操作成功！去“我的收藏”查看');
  };

  return (
    <div>
      <h2 className="page-title">公共广场</h2>
      
      <div className="card" style={{ marginBottom: '20px' }}>
        <div style={{ display: 'flex', gap: '10px' }}>
          <input className="chat-input" style={{ border: '1px solid #ccc', padding: '8px' }} placeholder="🔍 搜文档标题或作者..." value={keyword} onChange={e => setKeyword(e.target.value)} onKeyDown={e => e.key === 'Enter' && loadData(keyword)} />
          <button className="btn-primary" onClick={() => loadData(keyword)}>搜索</button>
        </div>
      </div>

      {/* 公开的收藏夹 */}
      <div className="card" style={{ marginBottom: '20px' }}>
        <h3>公开的收藏夹</h3>
        {folders.length === 0 && <p style={{color: '#999'}}>暂无公开收藏夹</p>}
        <div style={{ display: 'flex', gap: '10px', flexWrap: 'wrap' }}>
          {folders.map((f: any) => (
            <div key={f.id} style={{ border: '1px solid #eee', padding: '10px 15px', borderRadius: '8px', display: 'flex', gap: '10px', alignItems: 'center' }}>
              <span>📁 {f.name} <span style={{ fontSize: '12px', color: '#999' }}>(by {f.owner_name})</span></span>
              <button className="btn-primary" style={{ padding: '4px 8px', fontSize: '12px' }} onClick={() => handleFavFolder(f.id)}>收藏</button>
            </div>
          ))}
        </div>
      </div>

      {/* 公开的单文件 */}
      <div className="card">
        <h3>公开的单文件</h3>
        {docs.length === 0 && <p style={{color: '#999'}}>暂无公开文档</p>}
        <div style={{ display: 'flex', flexDirection: 'column', gap: '10px' }}>
          {docs.map((d: any) => (
            <div key={d.id} style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '15px', border: '1px solid #eee', borderRadius: '8px' }}>
              <div style={{ display: 'flex', alignItems: 'center', gap: '15px' }}>
                <div onClick={() => onViewUser(d.author_id)} style={{ cursor: 'pointer', textAlign: 'center' }}>
                  <div style={{ fontSize: '24px' }}>{d.author_avatar}</div>
                  <div style={{ fontSize: '12px', color: '#666' }}>{d.author_name}</div>
                </div>
                <div>📄 {d.title}</div>
              </div>
              <button className="btn-primary" style={{ padding: '6px 12px' }} onClick={() => handleFavDoc(d.id)}>收藏</button>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}