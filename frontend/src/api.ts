import axios from 'axios';

const api = axios.create({ baseURL: 'http://localhost:8000/api/v1' });

export const getCurrentUser = () => {
  const saved = localStorage.getItem('currentUser');
  if (saved) return JSON.parse(saved);
  return { id: 'u_zhangsan', name: '张三', avatar: '🧑‍💻' };
};

export const uploadFile = async (file: File, isPublic: boolean) => {
  const formData = new FormData();
  formData.append('file', file);
  const user = getCurrentUser();
  return (await api.post(`/documents/upload?user_id=${user.id}&is_public=${isPublic}`, formData)).data;
};

export const ingestUrl = async (url: string, isPublic: boolean) => {
  const user = getCurrentUser();
  return (await api.post(`/documents/url?user_id=${user.id}`, { url, is_public: isPublic })).data;
};

export const askQuestion = async (question: string) => (await api.post('/agent/ask', { question, top_k: 3 })).data;
export const getFolders = async () => (await api.get('/folders', { params: { user_id: getCurrentUser().id } })).data;
export const createFolder = async (name: string) => (await api.post('/folders', { name }, { params: { user_id: getCurrentUser().id } })).data;
export const getFolderDocs = async (folderId: string) => (await api.get(`/folders/${folderId}/documents`)).data;
export const getAllDocs = async () => (await api.get('/documents/all')).data;
export const getUncategorizedDocs = async () => (await api.get('/documents/uncategorized')).data;
export const moveDocToFolder = async (folderId: string, docId: string) => (await api.post(`/folders/${folderId}/documents/${docId}`)).data;
export const toggleDocVisibility = async (docId: string) => (await api.post(`/documents/${docId}/toggle-visibility`, {}, { params: { user_id: getCurrentUser().id } })).data;

export const getSquareDocs = async (keyword: string = '') => 
  (await api.get('/square', { params: { keyword, user_id: getCurrentUser().id } })).data;
export const getSquareFolders = async () => 
  (await api.get('/square/folders', { params: { user_id: getCurrentUser().id } })).data;
export const getUserPublicDocs = async (userId: string) => (await api.get(`/users/${userId}/docs`)).data;

// 收藏功能
export const toggleFavDoc = async (docId: string) => (await api.post(`/favorites/doc/${docId}`, {}, { params: { user_id: getCurrentUser().id } })).data;
export const toggleFavFolder = async (folderId: string) => (await api.post(`/favorites/folder/${folderId}`, {}, { params: { user_id: getCurrentUser().id } })).data;
export const getMyFavorites = async () => (await api.get('/favorites', { params: { user_id: getCurrentUser().id } })).data;
export const getDocContent = async (docId: string) => (await api.get(`/documents/${docId}/content`)).data;

export const removeDocFromFolder = async (folderId: string, docId: string) => 
  (await api.delete(`/folders/${folderId}/documents/${docId}`)).data;

export const deleteDoc = async (docId: string) => 
  (await api.delete(`/documents/${docId}`)).data;

export const toggleFolderPublic = async (folderId: string) => 
  (await api.post(`/folders/${folderId}/toggle-public`, {}, { params: { user_id: getCurrentUser().id } })).data;

export const getSquareFolderDocs = async (folderId: string) => 
  (await api.get(`/square/folders/${folderId}/docs`)).data;