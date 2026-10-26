import { useState, useEffect } from 'react';
import { 
  getFolders, createFolder, getFolderDocs, getAllDocs, getUncategorizedDocs, 
  moveDocToFolder, toggleDocVisibility, getDocContent, 
  removeDocFromFolder, deleteDoc, toggleFolderPublic // 👈 引入新接口
} from '../api';

export default function FolderView() {
  const [folders, setFolders] = useState<any[]>([]);
  const [newFolderName, setNewFolderName] = useState('');
  const [selectedFolder, setSelectedFolder] = useState<any>(null); 
  const [docs, setDocs] = useState<any[]>([]);
  const [searchFolder, setSearchFolder] = useState('');
  const [searchDocKeyword, setSearchDocKeyword] = useState('');
  
  // 预览相关的状态
  const [previewTitle, setPreviewTitle] = useState('');
  const [previewContent, setPreviewContent] = useState('');
  const [selectedDoc, setSelectedDoc] = useState<any>(null);

  useEffect(() => { 
    loadFolders(); 
    handleSelect(null); 
  }, []);

  const loadFolders = async () => { 
    try {
      const data = await getFolders();
      setFolders(data);
    } catch (e) { console.error(e); }
  };

  const handleCreate = async () => {
    if (!newFolderName.trim()) return;
    await createFolder(newFolderName); 
    setNewFolderName(''); 
    loadFolders();
  };

  const handleSelect = async (target: any) => {
    setSelectedFolder(target); 
    setSearchDocKeyword(''); 
    setPreviewTitle(''); 
    setSelectedDoc(null);
    
    try {
      let data = [];
      if (target === null) data = await getAllDocs();
      else if (target === 'uncategorized') data = await getUncategorizedDocs();
      else data = await getFolderDocs(target.id);
      setDocs(data);
    } catch (e) { console.error(e); }
  };

  const handleMoveToFolder = async (e: any, docId: string, folderId: string) => {
    e.stopPropagation();
    if (!folderId) return;
    await moveDocToFolder(folderId, docId); 
    handleSelect(selectedFolder); 
  };

  const handleRemoveFromFolder = async (e: any, docId: string) => {
    e.stopPropagation();
    if (!window.confirm('从当前收藏夹移出？（将变成未分类）')) return;
    await removeDocFromFolder(selectedFolder.id, docId);
    handleSelect(selectedFolder);
  };

  const handleDelete = async (e: any, docId: string) => {
    e.stopPropagation();
    if (!window.confirm('警告：确定要彻底删除这个文件吗？物理文件也将被删除！')) return;
    await deleteDoc(docId);
    if (selectedDoc?.id === docId) { setPreviewTitle(''); setSelectedDoc(null); }
    handleSelect(selectedFolder);
  };

  const handleToggleVisibility = async (e: any, docId: string) => {
    e.stopPropagation();
    await toggleDocVisibility(docId);
    handleSelect(selectedFolder);
  };

  // 👇 新增：切换收藏夹的公开状态
  const handleToggleFolderVisibility = async (e: any, folderId: string) => {
    e.stopPropagation(); // 阻止触发选中文件夹
    try {
      await toggleFolderPublic(folderId);
      loadFolders(); // 重新加载文件夹列表，刷新状态
      // 如果当前正在查看这个文件夹，也要同步更新右侧状态
      if (selectedFolder?.id === folderId) {
        setSelectedFolder((prev: any) => ({ ...prev, is_public: !prev.is_public }));
      }
    } catch (err) {
      console.error(err);
      alert('切换状态失败');
    }
  };

  const handleViewDoc = async (doc: any) => {
    setSelectedDoc(doc); 
    setPreviewTitle(doc.title); 
    setPreviewContent('加载中...');
    if (doc.source_type !== 'image' && doc.source_type !== 'video') {
      try { const res = await getDocContent(doc.id); setPreviewContent(res.content); } 
      catch (e) { setPreviewContent('加载失败'); }
    }
  };

  const filteredFolders = folders.filter(f => f.name.includes(searchFolder));
  const filteredDocs = docs.filter(d => d.title.toLowerCase().includes(searchDocKeyword.toLowerCase()));
  const canArchiveHere = selectedFolder === null || selectedFolder === 'uncategorized';

  return (
    <div>
      <h2 className="page-title">我的资料库</h2>
      
      <div className="card">
        <div style={{ display: 'flex', gap: '10px' }}>
          <input 
            className="chat-input" 
            style={{ border: '1px solid #ccc', padding: '8px' }} 
            placeholder="新建收藏夹..." 
            value={newFolderName} 
            onChange={e => setNewFolderName(e.target.value)} 
          />
          <button className="btn-primary" onClick={handleCreate}>新建</button>
        </div>
      </div>

      <div style={{ display: 'flex', gap: '20px' }}>
        
        {/* 左侧：目录列表 */}
        <div className="card" style={{ flex: 1, minHeight: '400px' }}>
          <input 
            className="chat-input" 
            style={{ border: '1px solid #ccc', padding: '6px', width: '100%', marginBottom: '10px' }} 
            placeholder="🔍 搜索目录..." 
            value={searchFolder} 
            onChange={e => setSearchFolder(e.target.value)} 
          />
          <ul style={{ listStyle: 'none', padding: 0 }}>
            <li onClick={() => handleSelect(null)} style={{ padding: '10px', cursor: 'pointer', fontWeight: 'bold', borderRadius: '8px', backgroundColor: selectedFolder === null ? '#EBE6F2' : 'transparent' }}>📥 全部资料</li>
            <li onClick={() => handleSelect('uncategorized')} style={{ padding: '10px', cursor: 'pointer', fontWeight: 'bold', borderRadius: '8px', backgroundColor: selectedFolder === 'uncategorized' ? '#EBE6F2' : 'transparent' }}>📭 未分类资料</li>
            <hr style={{ border: '0', borderTop: '1px solid #eee', margin: '10px 0' }}/>
            
            {filteredFolders.map(f => (
              <li key={f.id} style={{ 
                padding: '10px', cursor: 'pointer', borderRadius: '8px', 
                backgroundColor: selectedFolder?.id === f.id ? '#EBE6F2' : 'transparent',
                display: 'flex', justifyContent: 'space-between', alignItems: 'center'
              }}>
                {/* 文件夹名字区域 */}
                <div onClick={() => handleSelect(f)} style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {f.is_public ? '🌐 ' : '📁 '} {f.name}
                </div>
                
                {/* 👇 切换收藏夹公开状态按钮 */}
                <button 
                  onClick={(e) => handleToggleFolderVisibility(e, f.id)}
                  style={{ 
                    padding: '4px 6px', fontSize: '11px', border: 'none', borderRadius: '4px', 
                    background: f.is_public ? '#d1e7dd' : '#f8d7da', cursor: 'pointer', flexShrink: 0
                  }}
                >
                  {f.is_public ? '公开' : '私有'}
                </button>
              </li>
            ))}
          </ul>
        </div>

        {/* 中间：文件列表 */}
        <div className="card" style={{ flex: 1.5, minHeight: '400px' }}>
          <h3 style={{ margin: 0, marginBottom: '15px' }}>
            {selectedFolder === null ? '全部资料' : selectedFolder === 'uncategorized' ? '未分类资料' : `${selectedFolder.name} 的内容`}
          </h3>
          <input 
            className="chat-input" 
            style={{ border: '1px solid #ccc', padding: '8px', width: '100%', marginBottom: '15px' }} 
            placeholder="🔍 搜索文档名..." 
            value={searchDocKeyword} 
            onChange={e => setSearchDocKeyword(e.target.value)} 
          />
          
          <ul style={{ listStyle: 'none', padding: 0 }}>
            {filteredDocs.map(d => (
              <li key={d.id} onClick={() => handleViewDoc(d)} style={{ padding: '10px', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', alignItems: 'center', cursor: 'pointer', backgroundColor: previewTitle === d.title ? '#FAF8FC' : 'transparent' }}>
                
                <div style={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {d.is_public ? '🌐 ' : '🔒 '}{d.title}
                </div>

                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <button onClick={(e) => handleToggleVisibility(e, d.id)} style={{ padding: '4px 8px', fontSize: '12px', borderRadius: '4px', border: 'none', background: d.is_public ? '#f8d7da' : '#d1e7dd', cursor: 'pointer' }}>
                    {d.is_public ? '私有' : '公开'}
                  </button>

                  {/* 只有进入具体文件夹才显示移出按钮 */}
                  {selectedFolder && selectedFolder !== 'uncategorized' && (
                    <button onClick={(e) => handleRemoveFromFolder(e, d.id)} style={{ padding: '4px 8px', fontSize: '12px', border: '1px solid #ccc', borderRadius: '4px', cursor: 'pointer', background: '#fff' }}>
                      移出
                    </button>
                  )}

                  {/* 归档下拉框 */}
                  <select onClick={e => e.stopPropagation()} onChange={(e) => handleMoveToFolder(e, d.id, e.target.value)} defaultValue="" style={{ padding: '4px', borderRadius: '4px', border: '1px solid #ccc', fontSize: '12px' }}>
                    <option value="" disabled>分类...</option>
                    {folders.map(f => <option key={f.id} value={f.id}>{f.name}</option>)}
                  </select>

                  {/* 删除按钮 */}
                  <button onClick={(e) => handleDelete(e, d.id)} style={{ padding: '4px 8px', fontSize: '12px', border: 'none', borderRadius: '4px', cursor: 'pointer', background: '#d32f2f', color: 'white' }}>
                    删除
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {/* 右侧：多模态预览面板 */}
        {previewTitle && selectedDoc && (
          <div className="card" style={{ flex: 2, backgroundColor: '#FAF8FC', borderLeft: '4px solid #8B6EC1', maxHeight: '600px', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '15px' }}>
              <h3 style={{ color: '#8B6EC1', margin: 0 }}>📄 {previewTitle}</h3>
              <button onClick={() => setPreviewTitle('')} style={{ background: 'none', border: 'none', cursor: 'pointer', fontSize: '16px', color: '#999' }}>✖ 关闭</button>
            </div>

            {selectedDoc.source_type === 'image' && selectedDoc.source_url && (
              <img src={`http://localhost:8000${selectedDoc.source_url}`} style={{ maxWidth: '100%', borderRadius: '8px' }} />
            )}
            {selectedDoc.source_type === 'video' && selectedDoc.source_url && (
              <video src={`http://localhost:8000${selectedDoc.source_url}`} controls style={{ maxWidth: '100%', borderRadius: '8px' }} />
            )}
            {selectedDoc.source_type !== 'image' && selectedDoc.source_type !== 'video' && (
              <div style={{ whiteSpace: 'pre-wrap', fontSize: '14px', lineHeight: '1.6', color: '#333' }}>{previewContent}</div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}