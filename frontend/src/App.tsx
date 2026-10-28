import { useState } from 'react';
import UploadPanel from './components/UploadPanel';
import ChatArea from './components/ChatArea';
import FolderView from './components/FolderView';
import SquareView from './components/SquareView';
import UserProfileView from './components/UserProfileView';
import FavoriteView from './components/FavoriteView'; // 👈 确保引入了
import { getCurrentUser } from './api';
import MistakeView from './components/MistakeView';

function App() {
  const [activeTab, setActiveTab] = useState<'chat' | 'upload' | 'folder' | 'square' | 'profile' | 'favorite' | 'mistake'>('chat');
  const [currentUser, setCurrentUser] = useState(getCurrentUser());
  const [viewingUserId, setViewingUserId] = useState(''); 

  const handleSwitchUser = (e: any) => {
    const user = e.target.value === 'zhangsan' 
      ? { id: 'u_zhangsan', name: '张三', avatar: '🧑‍💻' }
      : { id: 'u_lisi', name: '李四', avatar: '👩‍💻' };
    localStorage.setItem('currentUser', JSON.stringify(user));
    setCurrentUser(user);
    window.location.reload(); 
  };

  return (
    <div className="app-layout">
      <div className="sidebar">
        <h2 className="sidebar-title">🧠 知识库</h2>
        
        <div className={`nav-item ${activeTab === 'chat' ? 'active' : ''}`} onClick={() => setActiveTab('chat')}>💬 AI 智能问答</div>
        <div className={`nav-item ${activeTab === 'upload' ? 'active' : ''}`} onClick={() => setActiveTab('upload')}>📤 资料上传收录</div>
        <div className={`nav-item ${activeTab === 'folder' ? 'active' : ''}`} onClick={() => setActiveTab('folder')}>📁 我的资料库</div>
        
        {/* 👇 确保这里有我的收藏 */}
        <div className={`nav-item ${activeTab === 'favorite' ? 'active' : ''}`} onClick={() => setActiveTab('favorite')}>⭐️ 我的收藏</div>
        <div className={`nav-item ${activeTab === 'mistake' ? 'active' : ''}`}onClick={() => setActiveTab('mistake')}>📝 错题管理</div>
        <div className={`nav-item ${activeTab === 'square' ? 'active' : ''}`} onClick={() => setActiveTab('square')}>🌐 公共广场</div>

        <div style={{ marginTop: 'auto', padding: '15px', borderTop: '1px solid #eee' }}>
          <div style={{ marginBottom: '10px', fontWeight: 'bold' }}>
            {currentUser.avatar} {currentUser.name}
          </div>
          <select onChange={handleSwitchUser} value={currentUser.id === 'u_zhangsan' ? 'zhangsan' : 'lisi'} style={{ width: '100%', padding: '5px' }}>
            <option value="zhangsan">切换为：张三</option>
            <option value="lisi">切换为：李四</option>
          </select>
        </div>
      </div>

      <div className="main-content">
        {activeTab === 'chat' && <><h1 className="page-title">AI 智能问答</h1><ChatArea /></>}
        {activeTab === 'upload' && <><h1 className="page-title">资料上传收录</h1><UploadPanel /></>}
        {activeTab === 'folder' && <FolderView />}
        
        {/* 👇 确保这里有我的收藏渲染 */}
        {activeTab === 'favorite' && <FavoriteView />}
        {activeTab === 'mistake' && <MistakeView />}
        {activeTab === 'square' && (
          <SquareView onViewUser={(uid) => { setViewingUserId(uid); setActiveTab('profile'); }} />
        )}
        {activeTab === 'profile' && (
          <UserProfileView userId={viewingUserId} onBack={() => setActiveTab('square')} />
        )}
      </div>
    </div>
  );
}

export default App;