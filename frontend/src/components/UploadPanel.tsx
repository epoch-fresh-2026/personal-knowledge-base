import { useState, useEffect } from 'react';
import { uploadFile, ingestUrl, getFolders, moveDocToFolder } from '../api';

export default function UploadPanel() {
  const [file, setFile] = useState<File | null>(null);
  const [url, setUrl] = useState('');
  const [folders, setFolders] = useState<any[]>([]);
  const [selectedFolderId, setSelectedFolderId] = useState<string>('');
  const [isPublic, setIsPublic] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => { getFolders().then(setFolders).catch(console.error); }, []);

  const handleUploadFile = async () => {
    if (!file) return alert('请先选择文件');
    try {
      setLoading(true);
      const res = await uploadFile(file, isPublic);
      if (selectedFolderId) await moveDocToFolder(selectedFolderId, res.id);
      alert('上传成功！');
      setFile(null);
    } catch (err) { alert('上传失败'); } finally { setLoading(false); }
  };

  const handleIngestUrl = async () => {
    if (!url.trim()) return alert('请输入网址');
    try {
      setLoading(true);
      const res = await ingestUrl(url, isPublic);
      if (selectedFolderId) await moveDocToFolder(selectedFolderId, res.id);
      alert('网页抓取入库成功！');
      setUrl('');
    } catch (err) { alert('抓取失败'); } finally { setLoading(false); }
  };

  return (
    <div className="card">
      <h3>📄 资料收录</h3>
      <div style={{ marginBottom: '15px', display: 'flex', alignItems: 'center', gap: '20px' }}>
        <div>
          <label>归档到收藏夹：</label>
          <select value={selectedFolderId} onChange={(e) => setSelectedFolderId(e.target.value)} style={{ marginLeft: '10px', padding: '5px' }}>
            <option value="">-- 不放入 --</option>
            {folders.map((f: any) => <option key={f.id} value={f.id}>{f.name}</option>)}
          </select>
        </div>
        <div>
          <label style={{ cursor: 'pointer' }}>
            <input type="checkbox" checked={isPublic} onChange={(e) => setIsPublic(e.target.checked)} /> 公开到广场
          </label>
        </div>
      </div>

      <div className="upload-box" style={{ marginBottom: '20px' }}>
        <input type="file" onChange={(e) => setFile(e.target.files?.[0] || null)} />
        <button className="btn-primary" onClick={handleUploadFile} disabled={loading || !file}>上传文件</button>
      </div>

      <hr style={{ border: '1px dashed #ccc', margin: '20px 0' }}/>

      <div className="upload-box">
        <input type="text" className="chat-input" style={{ border: '1px solid #ccc', padding: '8px' }}
          placeholder="粘贴网页链接 (如 https://...)" value={url} onChange={(e) => setUrl(e.target.value)} />
        <button className="btn-primary" onClick={handleIngestUrl} disabled={loading || !url.trim()}>抓取网页</button>
      </div>
    </div>
  );
}