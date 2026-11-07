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
export const moveDocToFolder = async (folderId: string, docId: string) => (await api.post(`/folders/${folderId}/documents/${docId}`)).data;
export const toggleDocVisibility = async (docId: string) => (await api.post(`/documents/${docId}/toggle-visibility`, {}, { params: { user_id: getCurrentUser().id } })).data;

// 👇 修复：加上 user_id 参数
export const getAllDocs = async () => 
  (await api.get('/documents/all', { params: { user_id: getCurrentUser().id } })).data;

// 👇 修复：加上 user_id 参数
export const getUncategorizedDocs = async () => 
  (await api.get('/documents/uncategorized', { params: { user_id: getCurrentUser().id } })).data;

export const getSquareDocs = async (keyword: string = '') => 
  (await api.get('/square', { params: { keyword, user_id: getCurrentUser().id } })).data;
export const getSquareFolders = async () => 
  (await api.get('/square/folders', { params: { user_id: getCurrentUser().id } })).data;
export const getUserPublicDocs = async (userId: string) => (await api.get(`/users/${userId}/docs`)).data;

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

export const deleteFolder = async (folderId: string) => 
  (await api.delete(`/folders/${folderId}`, { params: { user_id: getCurrentUser().id } })).data;

export const renameFolder = async (folderId: string, newName: string) => 
  (await api.put(`/folders/${folderId}/name`, { new_name: newName }, { params: { user_id: getCurrentUser().id } })).data;

// ==================== 薄弱知识点分析 ====================

export interface KnowledgePointItem {
  knowledge_point: string;
  total_mistakes: number;
  pending_count: number;
  reviewing_count: number;
  mastered_count: number;
  review_count: number;
  unmastered_count: number;
  weak_rate: number;
  status: 'weak' | 'mastered';
}

export interface KnowledgePointStatistics {
  user_id: string;
  total_knowledge_points: number;
  weak_knowledge_points: number;
  items: KnowledgePointItem[];
}

// 获取当前用户的知识点统计
export const getKnowledgePointStatistics = async (
  userId: string = getCurrentUser().id
): Promise<KnowledgePointStatistics> =>
  (
    await api.get('/mistakes/knowledge-points', {
      params: { user_id: userId },
    })
  ).data;

// ==================== 个性化智能复习建议 ====================

export interface ReviewRecommendationItem {
  mistake_id: string;
  question: string;
  knowledge_points: string[];
  status: 'pending' | 'reviewing';
  review_count: number;
  last_reviewed_at: string | null;
  days_since_last_review: number | null;
  priority: 'high' | 'medium' | 'low';
  priority_score: number;
  reasons: string[];
}

export interface ReviewRecommendationResponse {
  user_id: string;
  total_recommendations: number;
  returned_count: number;
  items: ReviewRecommendationItem[];
}

// 获取当前用户的智能复习建议
export const getReviewRecommendations = async (
  limit: number = 10
): Promise<ReviewRecommendationResponse> =>
  (
    await api.get('/mistakes/recommendations', {
      params: {
        user_id: getCurrentUser().id,
        limit,
      },
    })
  ).data;

// 记录一次复习并更新错题状态
export const completeMistakeReview = async (
  mistakeId: string,
  status: 'reviewing' | 'mastered'
) =>
  (
    await api.post(
      `/mistakes/${encodeURIComponent(mistakeId)}/review`,
      { status },
      {
        params: {
          user_id: getCurrentUser().id,
        },
      }
    )
  ).data;