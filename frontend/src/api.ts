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

export const getAllDocs = async () =>
  (await api.get('/documents/all', { params: { user_id: getCurrentUser().id } })).data;

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

// ==================== 学习数据统计与可视化 ====================

export interface LearningOverview {
  user_id: string;
  total_mistakes: number;
  total_reviews: number;
  recorded_review_count: number;
  mastered_mistakes: number;
  total_knowledge_points: number;
  weak_knowledge_points: number;
  status_distribution: {
    pending: number;
    reviewing: number;
    mastered: number;
  };
  knowledge_points: KnowledgePointItem[];
}

export interface LearningTrendItem {
  date: string;
  review_count: number;
  mastered_review_count: number;
  new_mistake_count: number;
}

export interface LearningTrendResponse {
  user_id: string;
  granularity: 'day' | 'week';
  start_date: string;
  end_date: string;
  days: number;
  items: LearningTrendItem[];
}

export const getLearningOverview = async (
  userId: string = getCurrentUser().id
): Promise<LearningOverview> =>
  (
    await api.get('/mistakes/analytics/overview', {
      params: { user_id: userId },
    })
  ).data;

export const getLearningTrends = async (
  days: number = 30,
  granularity: 'day' | 'week' = 'day',
  userId: string = getCurrentUser().id
): Promise<LearningTrendResponse> =>
  (
    await api.get('/mistakes/analytics/trends', {
      params: {
        user_id: userId,
        days,
        granularity,
      },
    })
  ).data;

// ==================== 标签管理 ====================

export interface TagItem {
  id: string;
  name: string;
  pinned: boolean;
}

export interface DocumentTagItem {
  id: string;
  name: string;
  pinned: boolean;
}

export interface TagDocumentItem {
  id: string;
  title: string;
  source_type: string;
  source_url: string | null;
  is_public: boolean;
  owner_id: string;
  tags: DocumentTagItem[];
}

// 获取全部标签
export const getAllTags = async (): Promise<TagItem[]> =>
  (await api.get('/tags')).data;

// 创建标签
export const createTag = async (name: string) =>
  (await api.post('/tags', { name })).data;

// 删除标签
export const deleteTag = async (tagId: string) =>
  (await api.delete(`/tags/${encodeURIComponent(tagId)}`)).data;

// 置顶或取消置顶标签
export const toggleTagPin = async (tagId: string) =>
  (await api.post(`/tags/${encodeURIComponent(tagId)}/pin`)).data;

// 给文档添加标签
export const addTagToDocument = async (
  docId: string,
  tagId: string
) =>
  (
    await api.post(
      `/documents/${encodeURIComponent(docId)}/tags/${encodeURIComponent(tagId)}`
    )
  ).data;

// 从文档移除标签
export const removeTagFromDocument = async (
  docId: string,
  tagId: string
) =>
  (
    await api.delete(
      `/documents/${encodeURIComponent(docId)}/tags/${encodeURIComponent(tagId)}`
    )
  ).data;

// 根据标签获取文档
export const getDocumentsByTag = async (tagName: string) =>
  (
    await api.get(`/tags/${encodeURIComponent(tagName)}/documents`)
  ).data;
