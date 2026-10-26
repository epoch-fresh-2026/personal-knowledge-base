import { useState, useEffect } from 'react';
import { getMyFavorites, toggleFavDoc, toggleFavFolder, getDocContent, getSquareFolderDocs } from '../api';

export default function FavoriteView() {
  const [data, setData] = useState<{documents: any[], folders: any[]}>({ documents: [], folders: [] });
  
  const [activeFolder, setActiveFolder] = useState<any>(null);
  const [folderFiles, setFolderFiles] = useState<any[]>([]);
  const [selectedDoc, setSelectedDoc] = useState<any>(null);
  const [previewContent, setPreviewContent] = useState('');

  useEffect(() => { loadFavorites(); }, []);

  const loadFavorites = () => { 
    getMyFavorites().then(setData).catch(console.error); 
  };

  const handleCancelDoc = async (e: any, docId: string) => {
    e.stopPropagation();
    if (!window.confirm('确定要取消收藏这个文件吗？')) return;
    await toggleFavDoc(docId);
    loadFavorites();
    if (selectedDoc?.id === docId) setSelectedDoc(null);
  };

  const handleCancelFolder = async (e: any, folderId: string) => {
    e.stopPropagation();
    if (!window.confirm('确定要取消收藏这个收藏夹吗？')) return;
    await toggleFavFolder(folderId);
    loadFavorites();
    if (activeFolder?.id === folderId) { setActiveFolder(null); setFolderFiles([]); setSelectedDoc(null); }
  };

  // 点击收藏夹
  const handleOpenFolder = async (folder: any) => {
    setSelectedDoc(null);
    setActiveFolder(folder);
    try { 
      const files = await getSquareFolderDocs(folder.id); 
      console.log("文件夹内部文件:", files); // 👈 方便调试
      setFolderFiles(files); 
    } catch (e) { console.error(e); }
  };

  // 点击单文件
  const handleOpenDoc = async (doc: any) => {
    setActiveFolder(null);
    setFolderFiles([]);
    setSelectedDoc(doc);
    setPreviewContent('加载中...');
    if (doc.source_type !== 'image' && doc.source_type !== 'video') {
      try { const res = await getDocContent(doc.id); setPreviewContent(res.content); } 
      catch (e) { setPreviewContent('加载失败'); }
    }
  };

  // 点击文件夹内的文件
  const handleViewFileInFolder = async (file: any) => {
    setSelectedDoc(file);
    setPreviewContent('加载中...');
    if (file.source_type !== 'image' && file.source_type !== 'video') {
      try { const res = await getDocContent(file.id); setPreviewContent(res.content); } 
      catch (e) { setPreviewContent('加载失败'); }
    }
  };

  return (
    <div>
      <h2 className="page-title">⭐️ 我的收藏</h2>
      <div style={{ display: 'flex', gap: '20px' }}>
        
        {/* 左侧列表 */}
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '20px' }}>
          <div className="card">
            <h3>收藏的单文件</h3>
            {data.documents.length === 0 && <p style={{color: '#999'}}>暂无收藏单文件</p>}
            {data.documents.map(d => (
              <div key={d.id} onClick={() => handleOpenDoc(d)} style={{ padding: '10px', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', cursor: 'pointer', backgroundColor: selectedDoc?.id === d.id ? '#FAF8FC' : 'transparent' }}>
                <div>📄 {d.title}</div>
                <button onClick={(e) => handleCancelDoc(e, d.id)} style={{ padding: '4px 8px', fontSize: '12px', background: '#f8d7da', border: 'none', borderRadius: '4px', color: '#d32f2f' }}>取消</button>
              </div>
            ))}
          </div>

          <div className="card">
            <h3>收藏的收藏夹</h3>
            {data.folders.length === 0 && <p style={{color: '#999'}}>暂无收藏夹</p>}
            {data.folders.map(f => (
              <div key={f.id} onClick={() => handleOpenFolder(f)} style={{ padding: '10px', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', cursor: 'pointer', backgroundColor: activeFolder?.id === f.id ? '#FAF8FC' : 'transparent' }}>
                <div>📁 {f.name}</div>
                <button onClick={(e) => handleCancelFolder(e, f.id)} style={{ padding: '4px 8px', fontSize: '12px', background: '#f8d7da', border: 'none', borderRadius: '4px', color: '#d32f2f' }}>取消</button>
              </div>
            ))}
          </div>
        </div>

        {/* 右侧预览区 */}
        <div className="card" style={{ flex: 1.5, backgroundColor: '#FAF8FC', borderLeft: '4px solid #8B6EC1', maxHeight: '600px', overflowY: 'auto' }}>
          
          {/* 优先判断：选中的是具体文件，渲染内容 */}
          {selectedDoc ? (
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '15px' }}>
                <div style={{ display: 'flex', gap: '10px', alignItems: 'center' }}>
                  {/* 👇 如果是从文件夹里点进来的，给个返回按钮 */}
                  {activeFolder && (
                    <button onClick={() => setSelectedDoc(null)} style={{ background: '#e9ecef', border: 'none', padding: '4px 8px', borderRadius: '4px', cursor: 'pointer', fontSize: '12px' }}>⬅ 返回列表</button>
                  )}
                  <h3 style={{ color: '#8B6EC1', margin: 0 }}>📄 {selectedDoc.title}</h3>
                </div>
                <button onClick={() => { setSelectedDoc(null); setActiveFolder(null); }} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#999' }}>✖ 关闭</button>
              </div>
              
              {selectedDoc.source_type === 'image' && selectedDoc.source_url && (
                <img src={`http://localhost:8000${selectedDoc.source_url}`} style={{ maxWidth: '100%', borderRadius: '8px' }} />
              )}
              {selectedDoc.source_type === 'video' && selectedDoc.source_url && (
                <video src={`http://localhost:8000${selectedDoc.source_url}`} controls style={{ maxWidth: '100%', borderRadius: '8px' }} />
              )}
              {selectedDoc.source_type !== 'image' && selectedDoc.source_type !== 'video' && (
                <div style={{ whiteSpace: 'pre-wrap', fontSize: '14px' }}>{previewContent}</div>
              )}
            </>
          ) : activeFolder ? (
            
          /* 其次判断：选中了文件夹，渲染文件列表 */
            <>
              <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '15px' }}>
                <h3 style={{ color: '#8B6EC1', margin: 0 }}>📁 {activeFolder.name} 的内容</h3>
                <button onClick={() => setActiveFolder(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#999' }}>✖ 关闭</button>
              </div>
              <div style={{ display: 'flex', gap: '10px', flexDirection: 'column' }}>
                {folderFiles.length === 0 && <p style={{ color: '#999' }}>文件夹为空或暂无公开文件</p>}
                {folderFiles.map(f => (
                  <div key={f.id} onClick={() => handleViewFileInFolder(f)} style={{ padding: '10px', border: '1px solid #eee', borderRadius: '4px', cursor: 'pointer', backgroundColor: selectedDoc?.id === f.id ? '#EBE6F2' : 'white' }}>
                    {f.source_type === 'image' ? '🖼️' : f.source_type === 'video' ? '🎬' : '📄'} {f.title}
                  </div>
                ))}
              </div>
            </>
          ) : (
            <p style={{ color: '#999', textAlign: 'center', marginTop: '50px' }}>点击左侧文件或收藏夹预览</p>
          )}

        </div>
      </div>
    </div>
  );
}