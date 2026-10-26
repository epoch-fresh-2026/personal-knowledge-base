import { useState, useEffect } from 'react';
import { getSquareDocs, getSquareFolders, toggleFavDoc, toggleFavFolder, getSquareFolderDocs, getDocContent } from '../api';

export default function SquareView({ onViewUser }: { onViewUser: (uid: string) => void }) {
  const [docs, setDocs] = useState<any[]>([]);
  const [folders, setFolders] = useState<any[]>([]);
  const [keyword, setKeyword] = useState('');

  const [activeFolder, setActiveFolder] = useState<any>(null);
  const [folderDocs, setFolderDocs] = useState<any[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<any>(null);
  const [previewContent, setPreviewContent] = useState('');

  useEffect(() => { loadData(''); }, []);

  const loadData = async (searchWord: string) => {
    try {
      const docsData = await getSquareDocs(searchWord);
      const foldersData = await getSquareFolders();
      setDocs(docsData);
      setFolders(foldersData);
      console.log("【广场数据刷新】文件列表:", docsData);
    } catch (e) { console.error(e); }
  };

  // 👇 加上了 console.log 调试
  const handleFavDoc = async (id: string) => {
    console.log("👉 准备收藏文档, ID:", id);
    try {
      const res = await toggleFavDoc(id);
      console.log("✅ 收藏接口返回:", res);
      await loadData(keyword); // 刷新列表状态
    } catch (e) { 
      console.error("❌ 收藏失败:", e); 
      alert("收藏失败，请检查后端");
    }
  };

  const handleFavFolder = async (id: string) => {
    console.log("👉 准备收藏文件夹, ID:", id);
    try {
      const res = await toggleFavFolder(id);
      console.log("✅ 收藏文件夹接口返回:", res);
      await loadData(keyword);
    } catch (e) { 
      console.error("❌ 收藏文件夹失败:", e); 
    }
  };

  const handleOpenFolder = async (folder: any) => {
    setActiveFolder(folder);
    setSelectedDoc(null);
    try {
      const data = await getSquareFolderDocs(folder.id);
      setFolderDocs(data);
    } catch (e) { console.error(e); }
  };

  const handleViewDocInFolder = async (doc: any) => {
    setSelectedDoc(doc);
    setPreviewContent('加载中...');
    if (doc.source_type !== 'image' && doc.source_type !== 'video') {
      try {
        const res = await getDocContent(doc.id);
        setPreviewContent(res.content);
      } catch (e) { setPreviewContent('内容加载失败'); }
    }
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
              <span onClick={() => handleOpenFolder(f)} style={{ cursor: 'pointer', color: '#8B6EC1', fontWeight: 'bold' }}>
                📁 {f.name}
              </span>
              <span style={{ fontSize: '12px', color: '#999' }}>(by {f.owner_name})</span>
              <button 
                onClick={(e) => {
                  e.preventDefault();
                  e.stopPropagation();
                  handleFavFolder(f.id);
                }}
                style={{ 
                  padding: '4px 8px', fontSize: '12px', borderRadius: '4px', border: 'none', cursor: 'pointer',
                  background: f.is_favorited ? '#e9ecef' : '#8B6EC1', 
                  color: f.is_favorited ? '#666' : 'white' 
                }}
              >
                {f.is_favorited ? '已收藏 (取消)' : '收藏'}
              </button>
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
              <button 
                onClick={(e) => {
                  e.preventDefault(); // 阻止默认行为
                  e.stopPropagation(); // 阻止事件冒泡
                  handleFavDoc(d.id); // 执行收藏
                }}
                style={{ 
                  padding: '6px 12px', fontSize: '14px', borderRadius: '4px', border: 'none', cursor: 'pointer',
                  background: d.is_favorited ? '#e9ecef' : '#8B6EC1', 
                  color: d.is_favorited ? '#666' : 'white'
                }}
              >
                {d.is_favorited ? '已收藏 (取消)' : '收藏'}
              </button>
            </div>
          ))}
        </div>
      </div>

      {/* 弹窗 */}
      {activeFolder && (
        <div style={{ position: 'fixed', top: 0, left: 0, width: '100vw', height: '100vh', backgroundColor: 'rgba(0,0,0,0.5)', display: 'flex', justifyContent: 'center', alignItems: 'center', zIndex: 1000 }}>
          <div className="card" style={{ width: '800px', maxHeight: '80vh', overflowY: 'auto', backgroundColor: 'white', display: 'flex', flexDirection: 'column' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '20px' }}>
              <h2 style={{ margin: 0, color: '#8B6EC1' }}>📁 {activeFolder.name} 的内容</h2>
              <button onClick={() => setActiveFolder(null)} style={{ background: 'none', border: 'none', fontSize: '20px', cursor: 'pointer' }}>✖</button>
            </div>
            <div style={{ display: 'flex', gap: '20px', flex: 1 }}>
              <div style={{ flex: 1, borderRight: '1px solid #eee', paddingRight: '20px' }}>
                {folderDocs.length === 0 && <p style={{color: '#999'}}>这个公开收藏夹还是空的。</p>}
                <ul style={{ listStyle: 'none', padding: 0 }}>
                  {folderDocs.map(d => (
                    <li 
                      key={d.id} 
                      onClick={() => handleViewDocInFolder(d)}
                      style={{ padding: '10px', borderBottom: '1px solid #f5f5f5', cursor: 'pointer', backgroundColor: selectedDoc?.id === d.id ? '#FAF8FC' : 'transparent' }}
                    >
                      {d.source_type === 'image' ? '🖼️' : d.source_type === 'video' ? '🎬' : '📄'} {d.title}
                    </li>
                  ))}
                </ul>
              </div>
              <div style={{ flex: 1.5 }}>
                {selectedDoc ? (
                  <>
                    <h4 style={{ margin: '0 0 15px 0' }}>{selectedDoc.title}</h4>
                    {selectedDoc.source_type === 'image' && selectedDoc.source_url && (
                      <img src={`http://localhost:8000${selectedDoc.source_url}`} style={{ maxWidth: '100%', borderRadius: '8px' }} />
                    )}
                    {selectedDoc.source_type === 'video' && selectedDoc.source_url && (
                      <video src={`http://localhost:8000${selectedDoc.source_url}`} controls style={{ maxWidth: '100%', borderRadius: '8px' }} />
                    )}
                    {selectedDoc.source_type !== 'image' && selectedDoc.source_type !== 'video' && (
                      <div style={{ whiteSpace: 'pre-wrap', fontSize: '14px', color: '#555' }}>{previewContent}</div>
                    )}
                  </>
                ) : (
                  <p style={{ color: '#999', textAlign: 'center', marginTop: '50px' }}>点击左侧文件预览内容</p>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}