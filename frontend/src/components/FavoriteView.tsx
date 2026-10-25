import { useState, useEffect } from 'react';
import { getMyFavorites, toggleFavDoc, toggleFavFolder, getDocContent, getFolderDocs } from '../api';

export default function FavoriteView() {
  const [data, setData] = useState<{documents: any[], folders: any[]}>({ documents: [], folders: [] });
  
  // 预览状态
  const [selectedDoc, setSelectedDoc] = useState<any>(null);
  const [previewContent, setPreviewContent] = useState('');
  const [folderFiles, setFolderFiles] = useState<any[]>([]);

  useEffect(() => { loadFavorites(); }, []);

  const loadFavorites = () => { getMyFavorites().then(setData).catch(console.error); };

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
  };

  // 点击查看详情
  const handleViewDoc = async (doc: any) => {
    setSelectedDoc(doc);
    setFolderFiles([]);
    setPreviewContent('加载中...');
    
    // 如果是图片或视频，不需要请求文本
    if (doc.source_type !== 'image' && doc.source_type !== 'video') {
      try {
        const res = await getDocContent(doc.id);
        setPreviewContent(res.content);
      } catch (e) { setPreviewContent('加载失败'); }
    }
  };

  const handleViewFolder = async (folder: any) => {
    setSelectedDoc({ title: `收藏夹：${folder.name}`, source_type: 'folder' });
    setPreviewContent('');
    try { setFolderFiles(await getFolderDocs(folder.id)); } catch (e) { console.error(e); }
  };

  return (
    <div>
      <h2 className="page-title">⭐️ 我的收藏</h2>
      <div style={{ display: 'flex', gap: '20px' }}>
        <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '20px' }}>
          
          <div className="card">
            <h3>收藏的单文件</h3>
            {data.documents.map(d => (
              <div key={d.id} onClick={() => handleViewDoc(d)} style={{ padding: '10px', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', cursor: 'pointer' }}>
                <div>📄 {d.title}</div>
                <button onClick={(e) => handleCancelDoc(e, d.id)} style={{ padding: '4px 8px', fontSize: '12px', background: '#f8d7da', border: 'none', borderRadius: '4px', color: '#d32f2f' }}>取消</button>
              </div>
            ))}
          </div>

          <div className="card">
            <h3>收藏的收藏夹</h3>
            {data.folders.map(f => (
              <div key={f.id} onClick={() => handleViewFolder(f)} style={{ padding: '10px', borderBottom: '1px solid #eee', display: 'flex', justifyContent: 'space-between', cursor: 'pointer' }}>
                <div>📁 {f.name}</div>
                <button onClick={(e) => handleCancelFolder(e, f.id)} style={{ padding: '4px 8px', fontSize: '12px', background: '#f8d7da', border: 'none', borderRadius: '4px', color: '#d32f2f' }}>取消</button>
              </div>
            ))}
          </div>
        </div>

        {/* 右侧预览区 */}
        {selectedDoc && (
          <div className="card" style={{ flex: 1.5, backgroundColor: '#FAF8FC', borderLeft: '4px solid #8B6EC1', maxHeight: '600px', overflowY: 'auto' }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '15px' }}>
              <h3 style={{ color: '#8B6EC1', margin: 0 }}>{selectedDoc.title}</h3>
              <button onClick={() => setSelectedDoc(null)} style={{ background: 'none', border: 'none', cursor: 'pointer', color: '#999' }}>✖ 关闭</button>
            </div>
            
            {/* 图片/视频渲染 */}
            {selectedDoc.source_type === 'image' && selectedDoc.source_url && (
              <img src={`http://localhost:8000${selectedDoc.source_url}`} style={{ maxWidth: '100%', borderRadius: '8px' }} />
            )}
            {selectedDoc.source_type === 'video' && selectedDoc.source_url && (
              <video src={`http://localhost:8000${selectedDoc.source_url}`} controls style={{ maxWidth: '100%', borderRadius: '8px' }} />
            )}

            {/* 文本渲染 */}
            {(selectedDoc.source_type !== 'image' && selectedDoc.source_type !== 'video' && selectedDoc.source_type !== 'folder') && (
              <div style={{ whiteSpace: 'pre-wrap', fontSize: '14px' }}>{previewContent}</div>
            )}

            {/* 收藏夹内容渲染 */}
            {selectedDoc.source_type === 'folder' && folderFiles.map(f => (
               <div key={f.id} style={{ padding: '10px', borderBottom: '1px dashed #ccc' }}>📄 {f.title}</div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}