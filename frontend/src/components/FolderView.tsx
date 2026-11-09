import { useState, useEffect } from 'react';
import {
  getFolders,
  createFolder,
  getFolderDocs,
  getAllDocs,
  getUncategorizedDocs,
  moveDocToFolder,
  toggleDocVisibility,
  getDocContent,
  removeDocFromFolder,
  deleteDoc,
  toggleFolderPublic,
  deleteFolder,
  renameFolder,
  getAllTags,
  createTag,
  deleteTag,
  toggleTagPin,
  addTagToDocument,
  removeTagFromDocument,
} from '../api';

export default function FolderView() {
  const [folders, setFolders] = useState<any[]>([]);
  const [newFolderName, setNewFolderName] = useState('');
  const [selectedFolder, setSelectedFolder] = useState<any>(null);
  const [docs, setDocs] = useState<any[]>([]);
  const [searchFolder, setSearchFolder] = useState('');
  const [searchDocKeyword, setSearchDocKeyword] = useState('');

  // 标签相关状态
  const [tags, setTags] = useState<any[]>([]);
  const [newTagName, setNewTagName] = useState('');

  // 预览相关状态
  const [previewTitle, setPreviewTitle] = useState('');
  const [previewContent, setPreviewContent] = useState('');
  const [selectedDoc, setSelectedDoc] = useState<any>(null);

  useEffect(() => {
    loadFolders();
    loadTags();
    handleSelect(null);
  }, []);

  const loadFolders = async () => {
    try {
      const data = await getFolders();
      setFolders(data);
    } catch (e) {
      console.error(e);
    }
  };

  const loadTags = async () => {
    try {
      const data = await getAllTags();
      setTags(data);
    } catch (e) {
      console.error('加载标签失败：', e);
    }
  };

  const handleCreate = async () => {
    if (!newFolderName.trim()) return;

    try {
      await createFolder(newFolderName.trim());
      setNewFolderName('');
      await loadFolders();
    } catch (e) {
      console.error(e);
      alert('创建收藏夹失败');
    }
  };

  const handleSelect = async (target: any) => {
    setSelectedFolder(target);
    setSearchDocKeyword('');
    setPreviewTitle('');
    setSelectedDoc(null);

    try {
      let data = [];

      if (target === null) {
        data = await getAllDocs();
      } else if (target === 'uncategorized') {
        data = await getUncategorizedDocs();
      } else {
        data = await getFolderDocs(target.id);
      }

      setDocs(data);
    } catch (e) {
      console.error(e);
    }
  };

  // 创建标签
  const handleCreateTag = async () => {
    const name = newTagName.trim();

    if (!name) {
      alert('请输入标签名称');
      return;
    }

    try {
      await createTag(name);
      setNewTagName('');
      await loadTags();
      alert('标签创建成功');
    } catch (e) {
      console.error(e);
      alert('创建标签失败，可能是标签名称重复');
    }
  };

  // 删除标签
  const handleDeleteTag = async (tagId: string, tagName: string) => {
    if (!window.confirm(`确定删除标签「${tagName}」吗？`)) return;

    try {
      await deleteTag(tagId);
      await loadTags();
      await handleSelect(selectedFolder);
      alert('标签已删除');
    } catch (e) {
      console.error(e);
      alert('删除标签失败');
    }
  };

  // 置顶或取消置顶
  const handleToggleTagPin = async (tagId: string) => {
    try {
      await toggleTagPin(tagId);
      await loadTags();
    } catch (e) {
      console.error(e);
      alert('修改标签置顶状态失败');
    }
  };

  // 给文档添加标签
  const handleAddTag = async (
    e: any,
    docId: string,
    tagId: string
  ) => {
    e.stopPropagation();

    if (!tagId) return;

    try {
      await addTagToDocument(docId, tagId);
      await handleSelect(selectedFolder);
    } catch (e) {
      console.error(e);
      alert('添加标签失败');
    }
  };

  // 从文档移除标签
  const handleRemoveTag = async (
    e: any,
    docId: string,
    tagId: string
  ) => {
    e.stopPropagation();

    try {
      await removeTagFromDocument(docId, tagId);
      await handleSelect(selectedFolder);
    } catch (e) {
      console.error(e);
      alert('移除标签失败');
    }
  };

  const handleMoveToFolder = async (
    e: any,
    docId: string,
    folderId: string
  ) => {
    e.stopPropagation();

    if (!folderId) return;

    try {
      await moveDocToFolder(folderId, docId);
      await handleSelect(selectedFolder);
    } catch (e) {
      console.error(e);
      alert('移动文档失败');
    }
  };

  const handleRemoveFromFolder = async (e: any, docId: string) => {
    e.stopPropagation();

    if (!window.confirm('从当前收藏夹移出？（将变成未分类）')) return;

    try {
      await removeDocFromFolder(selectedFolder.id, docId);
      await handleSelect(selectedFolder);
    } catch (e) {
      console.error(e);
      alert('移出失败');
    }
  };

  const handleDelete = async (e: any, docId: string) => {
    e.stopPropagation();

    if (
      !window.confirm(
        '警告：确定要彻底删除这个文件吗？物理文件也将被删除！'
      )
    ) {
      return;
    }

    try {
      await deleteDoc(docId);

      if (selectedDoc?.id === docId) {
        setPreviewTitle('');
        setSelectedDoc(null);
      }

      await handleSelect(selectedFolder);
    } catch (e) {
      console.error(e);
      alert('删除文档失败');
    }
  };

  const handleToggleVisibility = async (e: any, docId: string) => {
    e.stopPropagation();

    try {
      await toggleDocVisibility(docId);
      await handleSelect(selectedFolder);
    } catch (e) {
      console.error(e);
      alert('切换文档公开状态失败');
    }
  };

  const handleToggleFolderVisibility = async (
    e: any,
    folderId: string
  ) => {
    e.stopPropagation();

    try {
      await toggleFolderPublic(folderId);
      await loadFolders();

      if (selectedFolder?.id === folderId) {
        setSelectedFolder((prev: any) => ({
          ...prev,
          is_public: !prev.is_public,
        }));
      }
    } catch (err) {
      console.error(err);
      alert('切换状态失败');
    }
  };

  const handleDeleteFolder = async (
    e: any,
    folderId: string,
    folderName: string
  ) => {
    e.stopPropagation();

    if (
      !window.confirm(
        `确定要删除收藏夹【${folderName}】吗？里面的文件将会退回未分类。`
      )
    ) {
      return;
    }

    try {
      await deleteFolder(folderId);
      await loadFolders();

      if (selectedFolder?.id === folderId) {
        await handleSelect(null);
      }
    } catch (err) {
      console.error(err);
      alert('删除失败');
    }
  };

  const handleRenameFolder = async (
    e: any,
    folderId: string,
    currentName: string
  ) => {
    e.stopPropagation();

    const newName = window.prompt(
      `修改收藏夹【${currentName}】的名称：`,
      currentName
    );

    if (newName === null) return;

    if (!newName.trim()) {
      alert('名称不能为空');
      return;
    }

    try {
      await renameFolder(folderId, newName.trim());
      await loadFolders();

      if (selectedFolder?.id === folderId) {
        setSelectedFolder((prev: any) => ({
          ...prev,
          name: newName.trim(),
        }));
      }
    } catch (err) {
      console.error(err);
      alert('重命名失败');
    }
  };

  const handleViewDoc = async (doc: any) => {
    setSelectedDoc(doc);
    setPreviewTitle(doc.title);
    setPreviewContent('加载中...');

    if (
      doc.source_type !== 'image' &&
      doc.source_type !== 'video'
    ) {
      try {
        const res = await getDocContent(doc.id);
        setPreviewContent(res.content);
      } catch (e) {
        setPreviewContent('加载失败');
      }
    }
  };

  const filteredFolders = folders.filter((f) =>
    f.name.includes(searchFolder)
  );

  const filteredDocs = docs.filter((d) =>
    d.title.toLowerCase().includes(searchDocKeyword.toLowerCase())
  );

  const sortedTags = [...tags].sort(
    (a, b) => Number(b.pinned) - Number(a.pinned)
  );

  return (
    <div>
      <h2 className="page-title">我的资料库</h2>

      {/* 新建收藏夹 */}
      <div className="card">
        <div style={{ display: 'flex', gap: '10px' }}>
          <input
            className="chat-input"
            style={{
              border: '1px solid #ccc',
              padding: '8px',
            }}
            placeholder="新建收藏夹..."
            value={newFolderName}
            onChange={(e) => setNewFolderName(e.target.value)}
          />

          <button className="btn-primary" onClick={handleCreate}>
            新建
          </button>
        </div>
      </div>

      {/* 标签管理区域 */}
      <div className="card" style={{ marginTop: '15px' }}>
        <h3 style={{ marginTop: 0, marginBottom: '12px' }}>
          🏷️ 标签管理
        </h3>

        <div
          style={{
            display: 'flex',
            gap: '10px',
            marginBottom: '15px',
          }}
        >
          <input
            className="chat-input"
            style={{
              border: '1px solid #ccc',
              padding: '8px',
              flex: 1,
            }}
            placeholder="输入新标签名称..."
            value={newTagName}
            onChange={(e) => setNewTagName(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === 'Enter') handleCreateTag();
            }}
          />

          <button className="btn-primary" onClick={handleCreateTag}>
            创建标签
          </button>
        </div>

        <div
          style={{
            display: 'flex',
            flexWrap: 'wrap',
            gap: '10px',
          }}
        >
          {sortedTags.length === 0 && (
            <span style={{ color: '#999', fontSize: '13px' }}>
              暂无标签，请先创建标签
            </span>
          )}

          {sortedTags.map((tag) => (
            <div
              key={tag.id}
              style={{
                display: 'flex',
                alignItems: 'center',
                gap: '6px',
                padding: '6px 10px',
                border: '1px solid #ddd',
                borderRadius: '16px',
                background: tag.pinned ? '#fff4d6' : '#f5f5f5',
                fontSize: '13px',
              }}
            >
              <span>
                {tag.pinned ? '📌 ' : '🏷️ '}
                {tag.name}
              </span>

              <button
                onClick={() => handleToggleTagPin(tag.id)}
                title={tag.pinned ? '取消置顶' : '置顶标签'}
                style={{
                  border: 'none',
                  background: 'transparent',
                  cursor: 'pointer',
                  padding: '2px',
                }}
              >
                {tag.pinned ? '取消置顶' : '置顶'}
              </button>

              <button
                onClick={() => handleDeleteTag(tag.id, tag.name)}
                title="删除标签"
                style={{
                  border: 'none',
                  background: 'transparent',
                  color: '#d32f2f',
                  cursor: 'pointer',
                  padding: '2px',
                }}
              >
                删除
              </button>
            </div>
          ))}
        </div>
      </div>

      <div style={{ display: 'flex', gap: '20px', marginTop: '15px' }}>
        {/* 左侧：目录列表 */}
        <div className="card" style={{ flex: 1.2, minHeight: '400px' }}>
          <input
            className="chat-input"
            style={{
              border: '1px solid #ccc',
              padding: '6px',
              width: '100%',
              marginBottom: '10px',
            }}
            placeholder="🔍 搜索目录..."
            value={searchFolder}
            onChange={(e) => setSearchFolder(e.target.value)}
          />

          <ul style={{ listStyle: 'none', padding: 0 }}>
            <li
              onClick={() => handleSelect(null)}
              style={{
                padding: '10px',
                cursor: 'pointer',
                fontWeight: 'bold',
                borderRadius: '8px',
                backgroundColor:
                  selectedFolder === null ? '#EBE6F2' : 'transparent',
              }}
            >
              📥 全部资料
            </li>

            <li
              onClick={() => handleSelect('uncategorized')}
              style={{
                padding: '10px',
                cursor: 'pointer',
                fontWeight: 'bold',
                borderRadius: '8px',
                backgroundColor:
                  selectedFolder === 'uncategorized'
                    ? '#EBE6F2'
                    : 'transparent',
              }}
            >
              📭 未分类资料
            </li>

            <hr
              style={{
                border: '0',
                borderTop: '1px solid #eee',
                margin: '10px 0',
              }}
            />

            {filteredFolders.map((f) => (
              <li
                key={f.id}
                style={{
                  padding: '10px',
                  cursor: 'pointer',
                  borderRadius: '8px',
                  backgroundColor:
                    selectedFolder?.id === f.id
                      ? '#EBE6F2'
                      : 'transparent',
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'center',
                }}
              >
                <div
                  onClick={() => handleSelect(f)}
                  style={{
                    flex: 1,
                    overflow: 'hidden',
                    textOverflow: 'ellipsis',
                    whiteSpace: 'nowrap',
                  }}
                >
                  {f.is_public ? '🌐 ' : '📁 '}
                  {f.name}
                </div>

                <div style={{ display: 'flex', gap: '5px', flexShrink: 0 }}>
                  <button
                    onClick={(e) =>
                      handleRenameFolder(e, f.id, f.name)
                    }
                    style={{
                      padding: '4px 6px',
                      fontSize: '11px',
                      border: 'none',
                      borderRadius: '4px',
                      background: '#e2e3e5',
                      color: '#383d41',
                      cursor: 'pointer',
                    }}
                  >
                    改名
                  </button>

                  <button
                    onClick={(e) =>
                      handleToggleFolderVisibility(e, f.id)
                    }
                    style={{
                      padding: '4px 6px',
                      fontSize: '11px',
                      border: 'none',
                      borderRadius: '4px',
                      background: f.is_public ? '#d1e7dd' : '#f8d7da',
                      cursor: 'pointer',
                    }}
                  >
                    {f.is_public ? '公开' : '私有'}
                  </button>

                  <button
                    onClick={(e) =>
                      handleDeleteFolder(e, f.id, f.name)
                    }
                    style={{
                      padding: '4px 6px',
                      fontSize: '11px',
                      border: 'none',
                      borderRadius: '4px',
                      background: '#ffeaea',
                      color: '#d32f2f',
                      cursor: 'pointer',
                    }}
                  >
                    删除
                  </button>
                </div>
              </li>
            ))}
          </ul>
        </div>

        {/* 中间：文件列表 */}
        <div className="card" style={{ flex: 1.5, minHeight: '400px' }}>
          <h3 style={{ margin: 0, marginBottom: '15px' }}>
            {selectedFolder === null
              ? '全部资料'
              : selectedFolder === 'uncategorized'
                ? '未分类资料'
                : `${selectedFolder.name} 的内容`}
          </h3>

          <input
            className="chat-input"
            style={{
              border: '1px solid #ccc',
              padding: '8px',
              width: '100%',
              marginBottom: '15px',
            }}
            placeholder="🔍 搜索文档名..."
            value={searchDocKeyword}
            onChange={(e) => setSearchDocKeyword(e.target.value)}
          />

          <ul style={{ listStyle: 'none', padding: 0 }}>
            {filteredDocs.map((d) => (
              <li
                key={d.id}
                onClick={() => handleViewDoc(d)}
                style={{
                  padding: '10px',
                  borderBottom: '1px solid #eee',
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '8px',
                  cursor: 'pointer',
                  backgroundColor:
                    previewTitle === d.title ? '#FAF8FC' : 'transparent',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'center',
                    gap: '8px',
                  }}
                >
                  <div
                    style={{
                      flex: 1,
                      overflow: 'hidden',
                      textOverflow: 'ellipsis',
                      whiteSpace: 'nowrap',
                    }}
                  >
                    {d.is_public ? '🌐 ' : '🔒 '}
                    {d.title}
                  </div>

                  <div
                    style={{
                      display: 'flex',
                      gap: '8px',
                      alignItems: 'center',
                      flexShrink: 0,
                    }}
                  >
                    <button
                      onClick={(e) =>
                        handleToggleVisibility(e, d.id)
                      }
                      style={{
                        padding: '4px 8px',
                        fontSize: '12px',
                        borderRadius: '4px',
                        border: 'none',
                        background: d.is_public ? '#f8d7da' : '#d1e7dd',
                        cursor: 'pointer',
                      }}
                    >
                      {d.is_public ? '私有' : '公开'}
                    </button>

                    {selectedFolder &&
                      selectedFolder !== 'uncategorized' && (
                        <button
                          onClick={(e) =>
                            handleRemoveFromFolder(e, d.id)
                          }
                          style={{
                            padding: '4px 8px',
                            fontSize: '12px',
                            border: '1px solid #ccc',
                            borderRadius: '4px',
                            cursor: 'pointer',
                            background: '#fff',
                          }}
                        >
                          移出
                        </button>
                      )}

                    <select
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) =>
                        handleMoveToFolder(e, d.id, e.target.value)
                      }
                      defaultValue=""
                      style={{
                        padding: '4px',
                        borderRadius: '4px',
                        border: '1px solid #ccc',
                        fontSize: '12px',
                      }}
                    >
                      <option value="" disabled>
                        分类...
                      </option>

                      {folders.map((f) => (
                        <option key={f.id} value={f.id}>
                          {f.name}
                        </option>
                      ))}
                    </select>

                    <button
                      onClick={(e) => handleDelete(e, d.id)}
                      style={{
                        padding: '4px 8px',
                        fontSize: '12px',
                        border: 'none',
                        borderRadius: '4px',
                        cursor: 'pointer',
                        background: '#d32f2f',
                        color: 'white',
                      }}
                    >
                      删除
                    </button>
                  </div>
                </div>

                {/* 文档已有标签 */}
                <div
                  onClick={(e) => e.stopPropagation()}
                  style={{
                    display: 'flex',
                    flexWrap: 'wrap',
                    alignItems: 'center',
                    gap: '6px',
                  }}
                >
                  {(d.tags || []).map((tag: any) => (
                    <span
                      key={tag.id}
                      style={{
                        display: 'inline-flex',
                        alignItems: 'center',
                        gap: '4px',
                        padding: '3px 8px',
                        borderRadius: '12px',
                        background: tag.pinned ? '#fff0c2' : '#eee8f5',
                        color: '#694b91',
                        fontSize: '12px',
                      }}
                    >
                      {tag.pinned ? '📌 ' : ''}
                      {tag.name}

                      <button
                        onClick={(e) =>
                          handleRemoveTag(e, d.id, tag.id)
                        }
                        title="移除标签"
                        style={{
                          border: 'none',
                          background: 'transparent',
                          color: '#999',
                          cursor: 'pointer',
                          padding: 0,
                        }}
                      >
                        ×
                      </button>
                    </span>
                  ))}

                  {/* 给当前文档添加标签 */}
                  {tags.some(
                    (tag) =>
                      !(d.tags || []).some(
                        (docTag: any) => docTag.id === tag.id
                      )
                  ) && (
                    <select
                      defaultValue=""
                      onClick={(e) => e.stopPropagation()}
                      onChange={(e) =>
                        handleAddTag(e, d.id, e.target.value)
                      }
                      style={{
                        padding: '3px 6px',
                        fontSize: '12px',
                        border: '1px solid #ddd',
                        borderRadius: '5px',
                        background: '#fff',
                      }}
                    >
                      <option value="">+ 添加标签</option>

                      {sortedTags
                        .filter(
                          (tag) =>
                            !(d.tags || []).some(
                              (docTag: any) => docTag.id === tag.id
                            )
                        )
                        .map((tag) => (
                          <option key={tag.id} value={tag.id}>
                            {tag.pinned ? '📌 ' : ''}
                            {tag.name}
                          </option>
                        ))}
                    </select>
                  )}
                </div>
              </li>
            ))}
          </ul>

          {filteredDocs.length === 0 && (
            <p
              style={{
                textAlign: 'center',
                color: '#999',
                padding: '20px',
              }}
            >
              暂无文档
            </p>
          )}
        </div>

        {/* 右侧：多模态预览面板 */}
        {previewTitle && selectedDoc && (
          <div
            className="card"
            style={{
              flex: 2,
              backgroundColor: '#FAF8FC',
              borderLeft: '4px solid #8B6EC1',
              maxHeight: '600px',
              overflowY: 'auto',
            }}
          >
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '15px',
              }}
            >
              <h3 style={{ color: '#8B6EC1', margin: 0 }}>
                📄 {previewTitle}
              </h3>

              <button
                onClick={() => {
                  setPreviewTitle('');
                  setSelectedDoc(null);
                }}
                style={{
                  background: 'none',
                  border: 'none',
                  cursor: 'pointer',
                  fontSize: '16px',
                  color: '#999',
                }}
              >
                ✖ 关闭
              </button>
            </div>

            {selectedDoc.source_type === 'image' &&
              selectedDoc.source_url && (
                <img
                  src={`http://localhost:8000${selectedDoc.source_url}`}
                  style={{
                    maxWidth: '100%',
                    borderRadius: '8px',
                  }}
                />
              )}

            {selectedDoc.source_type === 'video' &&
              selectedDoc.source_url && (
                <video
                  src={`http://localhost:8000${selectedDoc.source_url}`}
                  controls
                  style={{ maxWidth: '100%' }}
                />
              )}

            {selectedDoc.source_type !== 'image' &&
              selectedDoc.source_type !== 'video' && (
                <div
                  style={{
                    whiteSpace: 'pre-wrap',
                    fontSize: '14px',
                    lineHeight: '1.6',
                    color: '#333',
                  }}
                >
                  {previewContent}
                </div>
              )}
          </div>
        )}
      </div>
    </div>
  );
}