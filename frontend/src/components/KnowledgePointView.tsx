import { useCallback, useEffect, useState } from 'react';
import {
  getKnowledgePointStatistics,
  type KnowledgePointStatistics,
  type KnowledgePointItem,
} from '../api';

function KnowledgePointView() {
  const [data, setData] = useState<KnowledgePointStatistics | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const loadStatistics = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const result = await getKnowledgePointStatistics();
      setData(result);
    } catch {
      setError('知识点统计加载失败，请检查后端服务。');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadStatistics();
  }, [loadStatistics]);

  const summaryCards = [
    {
      label: '知识点总数',
      value: data?.total_knowledge_points ?? 0,
      color: '#2563eb',
      description: '已关联错题的知识点',
    },
    {
      label: '薄弱知识点',
      value: data?.weak_knowledge_points ?? 0,
      color: '#dc2626',
      description: '仍有未掌握错题',
    },
    {
      label: '已掌握知识点',
      value:
        (data?.total_knowledge_points ?? 0) -
        (data?.weak_knowledge_points ?? 0),
      color: '#16a34a',
      description: '关联错题均已掌握',
    },
  ];

  return (
    <div
      style={{
        padding: 24,
        maxWidth: 1100,
        margin: '0 auto',
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
            薄弱知识点分析
          </h1>
          <p style={{ color: '#6b7280', marginTop: 8 }}>
            根据错题和复习记录，了解自己的知识掌握情况。
          </p>
        </div>

        <button
          onClick={() => void loadStatistics()}
          disabled={loading}
          style={{
            padding: '9px 16px',
            border: '1px solid #d1d5db',
            borderRadius: 6,
            background: '#fff',
            cursor: loading ? 'not-allowed' : 'pointer',
          }}
        >
          {loading ? '加载中...' : '刷新数据'}
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

      {/* 加载状态 */}
      {loading && !data && (
        <div style={{ padding: 40, textAlign: 'center', color: '#6b7280' }}>
          正在加载知识点统计...
        </div>
      )}

      {data && (
        <>
          {/* 数据概览 */}
          <div
            style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(180px, 1fr))',
              gap: 16,
              marginBottom: 28,
            }}
          >
            {summaryCards.map((card) => (
              <div
                key={card.label}
                style={{
                  padding: 22,
                  background: '#fff',
                  border: '1px solid #e5e7eb',
                  borderRadius: 10,
                  boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
                }}
              >
                <div style={{ color: '#6b7280', fontSize: 14 }}>
                  {card.label}
                </div>

                <div
                  style={{
                    fontSize: 30,
                    fontWeight: 700,
                    color: card.color,
                    margin: '12px 0 8px',
                  }}
                >
                  {card.value}
                </div>

                <div style={{ color: '#9ca3af', fontSize: 12 }}>
                  {card.description}
                </div>
              </div>
            ))}
          </div>

          {/* 知识点列表 */}
          <div
            style={{
              background: '#fff',
              border: '1px solid #e5e7eb',
              borderRadius: 10,
              padding: 22,
            }}
          >
            <h2 style={{ fontSize: 19, marginTop: 0, marginBottom: 8 }}>
              知识点掌握情况
            </h2>

            <p
              style={{
                color: '#9ca3af',
                fontSize: 13,
                marginTop: 0,
                marginBottom: 20,
              }}
            >
              按未掌握错题数量和薄弱率排序。
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
                  📚
                </div>
                <div style={{ fontSize: 15, color: '#6b7280' }}>
                  暂无知识点统计数据
                </div>
                <div style={{ fontSize: 13, marginTop: 8 }}>
                  添加错题并填写关联知识点后，这里会显示分析结果。
                </div>
              </div>
            ) : (
              <div>
                {data.items.map((item: KnowledgePointItem) => (
                  <KnowledgePointCard
                    key={item.knowledge_point}
                    item={item}
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

function KnowledgePointCard({
  item,
}: {
  item: KnowledgePointItem;
}) {
  const total = item.total_mistakes;
  const rate = Math.round(item.weak_rate * 100);

  const pendingWidth =
    total > 0 ? (item.pending_count / total) * 100 : 0;

  const reviewingWidth =
    total > 0 ? (item.reviewing_count / total) * 100 : 0;

  const masteredWidth =
    total > 0 ? (item.mastered_count / total) * 100 : 0;

  const isWeak = item.status === 'weak';

  return (
    <div
      style={{
        padding: '20px 0',
        borderBottom: '1px solid #f0f0f0',
      }}
    >
      {/* 知识点名称与状态 */}
      <div
        style={{
          display: 'flex',
          justifyContent: 'space-between',
          alignItems: 'center',
          flexWrap: 'wrap',
          gap: 10,
          marginBottom: 15,
        }}
      >
        <div style={{ fontWeight: 600, fontSize: 16 }}>
          {item.knowledge_point}
        </div>

        <span
          style={{
            padding: '4px 10px',
            borderRadius: 20,
            fontSize: 12,
            background: isWeak ? '#fef2f2' : '#f0fdf4',
            color: isWeak ? '#dc2626' : '#16a34a',
          }}
        >
          {isWeak ? '需要加强' : '已掌握'}
        </span>
      </div>

      {/* 统计指标 */}
      <div
        style={{
          display: 'grid',
          gridTemplateColumns: 'repeat(auto-fit, minmax(110px, 1fr))',
          gap: 12,
          marginBottom: 16,
        }}
      >
        <Metric label="错题总数" value={total} />
        <Metric label="待复习" value={item.pending_count} />
        <Metric label="复习中" value={item.reviewing_count} />
        <Metric label="已掌握" value={item.mastered_count} />
        <Metric label="累计复习" value={item.review_count} />
        <Metric label="薄弱率" value={`${rate}%`} />
      </div>

      {/* 状态分布条 */}
      <div
        style={{
          display: 'flex',
          height: 9,
          overflow: 'hidden',
          borderRadius: 10,
          background: '#f3f4f6',
        }}
      >
        {item.pending_count > 0 && (
          <div
            title={`待复习：${item.pending_count}`}
            style={{
              width: `${pendingWidth}%`,
              background: '#ef4444',
            }}
          />
        )}

        {item.reviewing_count > 0 && (
          <div
            title={`复习中：${item.reviewing_count}`}
            style={{
              width: `${reviewingWidth}%`,
              background: '#f59e0b',
            }}
          />
        )}

        {item.mastered_count > 0 && (
          <div
            title={`已掌握：${item.mastered_count}`}
            style={{
              width: `${masteredWidth}%`,
              background: '#22c55e',
            }}
          />
        )}
      </div>

      <div
        style={{
          display: 'flex',
          gap: 18,
          flexWrap: 'wrap',
          marginTop: 10,
          fontSize: 12,
          color: '#6b7280',
        }}
      >
        <span>🔴 待复习</span>
        <span>🟠 复习中</span>
        <span>🟢 已掌握</span>
      </div>
    </div>
  );
}

function Metric({
  label,
  value,
}: {
  label: string;
  value: string | number;
}) {
  return (
    <div>
      <div style={{ color: '#9ca3af', fontSize: 12 }}>
        {label}
      </div>
      <div style={{ fontSize: 17, fontWeight: 600, marginTop: 5 }}>
        {value}
      </div>
    </div>
  );
}

export default KnowledgePointView;