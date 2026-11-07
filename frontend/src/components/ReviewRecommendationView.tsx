import { useCallback, useEffect, useState } from 'react';
import {
  getReviewRecommendations,
  completeMistakeReview,
  type ReviewRecommendationResponse,
  type ReviewRecommendationItem,
} from '../api';

const priorityLabels = {
  high: '优先复习',
  medium: '建议复习',
  low: '适当巩固',
};

const priorityColors = {
  high: '#dc2626',
  medium: '#d97706',
  low: '#2563eb',
};

const statusLabels = {
  pending: '待复习',
  reviewing: '复习中',
};

function ReviewRecommendationView() {
  const [data, setData] =
    useState<ReviewRecommendationResponse | null>(null);

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [reviewingId, setReviewingId] = useState<string | null>(null);
  const [notice, setNotice] = useState('');

  // 获取复习建议
  const loadRecommendations = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const result = await getReviewRecommendations(10);
      setData(result);
    } catch {
      setError('复习建议加载失败，请检查后端服务。');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadRecommendations();
  }, [loadRecommendations]);

  // 完成一次复习
  const handleReview = async (
    mistakeId: string,
    status: 'reviewing' | 'mastered'
  ) => {
    setReviewingId(mistakeId);
    setNotice('');
    setError('');

    try {
      await completeMistakeReview(mistakeId, status);

      setNotice(
        status === 'mastered'
          ? '复习完成，已标记为掌握！'
          : '复习记录成功，状态已更新为复习中。'
      );

      // 重新获取推荐结果
      await loadRecommendations();
    } catch {
      setError('复习操作失败，请检查后端服务。');
    } finally {
      setReviewingId(null);
    }
  };

  // 统计不同优先级的推荐数量
  const highCount =
    data?.items.filter((item) => item.priority === 'high').length ?? 0;

  const mediumCount =
    data?.items.filter((item) => item.priority === 'medium').length ?? 0;

  return (
    <div
      style={{
        maxWidth: 1100,
        margin: '0 auto',
        padding: 24,
      }}
    >
      {/* 页面标题 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 24,
        }}
      >
        <div>
          <h1 style={{ margin: 0, fontSize: 26 }}>
            个性化智能复习建议
          </h1>

          <p style={{ color: '#6b7280', marginTop: 8 }}>
            根据错题状态和薄弱知识点，为你安排复习优先级。
          </p>
        </div>

        <button
          onClick={() => {
            setNotice('');
            void loadRecommendations();
          }}
          disabled={loading}
          style={{
            padding: '9px 16px',
            border: '1px solid #d1d5db',
            borderRadius: 6,
            background: '#fff',
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? '加载中...' : '刷新建议'}
        </button>
      </div>

      {/* 错误提示 */}
      {error && (
        <div
          style={{
            padding: 14,
            marginBottom: 20,
            borderRadius: 8,
            background: '#fef2f2',
            color: '#dc2626',
          }}
        >
          {error}
        </div>
      )}

      {/* 成功提示 */}
      {notice && (
        <div
          style={{
            padding: 14,
            marginBottom: 20,
            borderRadius: 8,
            background: '#f0fdf4',
            color: '#16a34a',
          }}
        >
          {notice}
        </div>
      )}

      {/* 加载状态 */}
      {loading && !data && (
        <div
          style={{
            padding: 40,
            textAlign: 'center',
            color: '#6b7280',
          }}
        >
          正在生成复习建议...
        </div>
      )}

      {data && (
        <>
          {/* 推荐概览 */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 16,
              marginBottom: 28,
            }}
          >
            <SummaryCard
              label="推荐复习总数"
              value={data.total_recommendations}
              color="#2563eb"
            />

            <SummaryCard
              label="高优先级"
              value={highCount}
              color="#dc2626"
            />

            <SummaryCard
              label="中优先级"
              value={mediumCount}
              color="#d97706"
            />
          </div>

          {/* 推荐列表 */}
          <div
            style={{
              background: '#fff',
              border: '1px solid #e5e7eb',
              borderRadius: 10,
              padding: 22,
            }}
          >
            <h2 style={{ fontSize: 19, marginTop: 0 }}>
              推荐复习任务
            </h2>

            <p
              style={{
                color: '#9ca3af',
                fontSize: 13,
                marginTop: 0,
                marginBottom: 20,
              }}
            >
              根据复习状态、薄弱知识点和最近复习时间综合排序。
              当前展示 {data.returned_count} 条建议。
            </p>

            {data.items.length === 0 ? (
              <div
                style={{
                  padding: '45px 15px',
                  textAlign: 'center',
                  color: '#9ca3af',
                }}
              >
                <div style={{ fontSize: 36, marginBottom: 12 }}>
                  🎉
                </div>

                <div style={{ fontSize: 15, color: '#6b7280' }}>
                  暂无需要复习的错题
                </div>

                <div style={{ fontSize: 13, marginTop: 8 }}>
                  添加错题并设置复习状态后，系统会生成复习建议。
                </div>
              </div>
            ) : (
              <div>
                {data.items.map((item) => (
                  <RecommendationCard
                    key={item.mistake_id}
                    item={item}
                    busy={reviewingId === item.mistake_id}
                    onReview={(status) =>
                      handleReview(item.mistake_id, status)
                    }
                  />
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}

// 推荐概览卡片
function SummaryCard({
  label,
  value,
  color,
}: {
  label: string;
  value: number;
  color: string;
}) {
  return (
    <div
      style={{
        padding: 22,
        background: '#fff',
        border: '1px solid #e5e7eb',
        borderRadius: 10,
        boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
      }}
    >
      <div style={{ color: '#6b7280', fontSize: 14 }}>
        {label}
      </div>

      <div
        style={{
          fontSize: 30,
          fontWeight: 700,
          color,
          marginTop: 12,
        }}
      >
        {value}
      </div>
    </div>
  );
}

// 单条推荐卡片
function RecommendationCard({
  item,
  busy,
  onReview,
}: {
  item: ReviewRecommendationItem;
  busy: boolean;
  onReview: (status: 'reviewing' | 'mastered') => void;
}) {
  const elapsedText =
    item.days_since_last_review === null
      ? '尚无复习时间记录'
      : item.days_since_last_review === 0
        ? '今天复习过'
        : `${item.days_since_last_review} 天前复习`;

  return (
    <div
      style={{
        padding: '20px 0',
        borderBottom: '1px solid #f0f0f0',
      }}
    >
      {/* 优先级和题目 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'flex-start',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 12,
        }}
      >
        <div style={{ flex: 1, minWidth: 200 }}>
          <div
            style={{
              fontSize: 16,
              fontWeight: 600,
              lineHeight: 1.6,
              marginBottom: 8,
            }}
          >
            {item.question}
          </div>

          {/* 复习状态和知识点 */}
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 8,
              fontSize: 12,
            }}
          >
            <span
              style={{
                padding: '3px 9px',
                borderRadius: 20,
                background: '#f3f4f6',
                color: '#4b5563',
              }}
            >
              {statusLabels[item.status]}
            </span>

            {item.knowledge_points.map((point) => (
              <span
                key={point}
                style={{
                  padding: '3px 9px',
                  borderRadius: 20,
                  background: '#eff6ff',
                  color: '#2563eb',
                }}
              >
                {point}
              </span>
            ))}
          </div>
        </div>

        {/* 优先级 */}
        <span
          style={{
            flexShrink: 0,
            padding: '5px 11px',
            borderRadius: 20,
            fontSize: 12,
            fontWeight: 600,
            color: priorityColors[item.priority],
            background:
              item.priority === 'high'
                ? '#fef2f2'
                : item.priority === 'medium'
                  ? '#fffbeb'
                  : '#eff6ff',
          }}
        >
          {priorityLabels[item.priority]}
        </span>
      </div>

      {/* 推荐信息 */}
      <div
        style={{
          display: 'flex',
          flexWrap: 'wrap',
          gap: 18,
          color: '#6b7280',
          fontSize: 13,
          marginBottom: 14,
        }}
      >
        <span>累计复习：{item.review_count} 次</span>
        <span>{elapsedText}</span>
        <span>推荐评分：{item.priority_score}</span>
      </div>

      {/* 推荐理由 */}
      <div
        style={{
          padding: 14,
          borderRadius: 8,
          background: '#f9fafb',
        }}
      >
        <div
          style={{
            fontSize: 13,
            fontWeight: 600,
            color: '#374151',
            marginBottom: 8,
          }}
        >
          推荐理由
        </div>

        {item.reasons.map((reason, index) => (
          <div
            key={index}
            style={{
              fontSize: 13,
              color: '#6b7280',
              lineHeight: 1.8,
            }}
          >
            · {reason}
          </div>
        ))}
      </div>

      {/* 复习操作 */}
      <div
        style={{
          display: 'flex',
          gap: 10,
          flexWrap: 'wrap',
          marginTop: 16,
        }}
      >
        <button
          type="button"
          disabled={busy}
          onClick={() => onReview('reviewing')}
          style={{
            padding: '8px 14px',
            border: '1px solid #d1d5db',
            borderRadius: 6,
            background: '#fff',
            cursor: busy ? 'not-allowed' : 'pointer',
            opacity: busy ? 0.6 : 1,
          }}
        >
          {busy ? '处理中...' : '完成一次复习'}
        </button>

        <button
          type="button"
          disabled={busy}
          onClick={() => onReview('mastered')}
          style={{
            padding: '8px 14px',
            border: 'none',
            borderRadius: 6,
            background: '#2563eb',
            color: '#fff',
            cursor: busy ? 'not-allowed' : 'pointer',
            opacity: busy ? 0.6 : 1,
          }}
        >
          复习并标记为已掌握
        </button>
      </div>
    </div>
  );
}

export default ReviewRecommendationView;