
import { useCallback, useEffect, useState } from 'react';

import {
  getLearningOverview,
  getLearningTrends,
  type LearningOverview,
  type LearningTrendResponse,
  type LearningTrendItem,
} from '../api';

type Granularity = 'day' | 'week';

const colors = {
  pending: '#e58a58',
  reviewing: '#e6bd55',
  mastered: '#55a982',
  review: '#3b82f6',
  newMistake: '#e58a58',
  masteredReview: '#55a982',
};

function LearningAnalyticsView() {
  const [overview, setOverview] =
    useState<LearningOverview | null>(null);

  const [trends, setTrends] =
    useState<LearningTrendResponse | null>(null);

  const [days, setDays] = useState(30);
  const [granularity, setGranularity] =
    useState<Granularity>('day');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  // 加载学习统计数据
  const loadData = useCallback(async () => {
    setLoading(true);
    setError('');

    try {
      const [overviewResult, trendsResult] = await Promise.all([
        getLearningOverview(),
        getLearningTrends(days, granularity),
      ]);

      setOverview(overviewResult);
      setTrends(trendsResult);
    } catch {
      setError('学习数据加载失败，请检查后端服务。');
    } finally {
      setLoading(false);
    }
  }, [days, granularity]);

  // 初次加载及统计范围变化时获取数据
  useEffect(() => {
    let cancelled = false;

    const fetchData = async () => {
      try {
        const [overviewResult, trendsResult] = await Promise.all([
          getLearningOverview(),
          getLearningTrends(days, granularity),
        ]);

        if (!cancelled) {
          setOverview(overviewResult);
          setTrends(trendsResult);
          setError('');
        }
      } catch {
        if (!cancelled) {
          setError('学习数据加载失败，请检查后端服务。');
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    };

    void fetchData();

    return () => {
      cancelled = true;
    };
  }, [days, granularity]);

  const summaryCards = [
    {
      label: '错题总数',
      value: overview?.total_mistakes ?? 0,
      description: '当前记录的全部错题',
      color: '#2563eb',
    },
    {
      label: '累计复习次数',
      value: overview?.total_reviews ?? 0,
      description: '包含历史累计复习记录',
      color: '#7c3aed',
    },
    {
      label: '已掌握错题',
      value: overview?.mastered_mistakes ?? 0,
      description: '当前标记为已掌握',
      color: '#16a34a',
    },
    {
      label: '知识点总数',
      value: overview?.total_knowledge_points ?? 0,
      description: '已关联错题的知识点',
      color: '#d97706',
    },
  ];

  return (
    <div
      style={{
        maxWidth: 1150,
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
          <h1 style={{ fontSize: 26, margin: 0 }}>
            学习数据统计
          </h1>

          <p style={{ color: '#6b7280', marginTop: 8 }}>
            记录学习过程，了解错题复习情况和知识点掌握程度。
          </p>
        </div>

        <button
          type="button"
          disabled={loading}
          onClick={() => void loadData()}
          style={buttonStyle}
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
      {loading && !overview && (
        <div
          style={{
            padding: 40,
            textAlign: 'center',
            color: '#6b7280',
          }}
        >
          正在加载学习数据...
        </div>
      )}

      {overview && (
        <>
          {/* 一、学习数据概览 */}
          <section style={{ marginBottom: 28 }}>
            <SectionTitle
              title="学习数据概览"
              description="查看当前学习数据的整体情况。"
            />

            <div
              style={{
                display: 'grid',
                gridTemplateColumns:
                  'repeat(auto-fit, minmax(180px, 1fr))',
                gap: 16,
              }}
            >
              {summaryCards.map((card) => (
                <SummaryCard
                  key={card.label}
                  {...card}
                />
              ))}
            </div>

            <div
              style={{
                marginTop: 12,
                fontSize: 12,
                color: '#9ca3af',
              }}
            >
              当前已记录的复习历史：{overview.recorded_review_count} 次。
              该数量仅统计复习历史表中的实际记录。
            </div>
          </section>

          {/* 二、错题状态分布 */}
          <section style={{ marginBottom: 28 }}>
            <div style={panelStyle}>
              <SectionTitle
                title="错题状态分布"
                description="统计待复习、复习中和已掌握的错题数量。"
              />

              <StatusDistribution
                distribution={overview.status_distribution}
              />
            </div>
          </section>

          {/* 三、学习趋势 */}
          <section style={{ marginBottom: 28 }}>
            <div style={panelStyle}>
              <div
                style={{
                  display: 'flex',
                  justifyContent: 'space-between',
                  alignItems: 'flex-start',
                  flexWrap: 'wrap',
                  gap: 16,
                  marginBottom: 20,
                }}
              >
                <SectionTitle
                  title="学习趋势"
                  description="根据真实复习历史统计学习活动变化。"
                />

                <div
                  style={{
                    display: 'flex',
                    gap: 8,
                    flexWrap: 'wrap',
                  }}
                >
                  {[7, 30, 90].map((value) => (
                    <button
                      key={value}
                      type="button"
                      onClick={() => setDays(value)}
                      style={choiceStyle(days === value)}
                    >
                      {value} 天
                    </button>
                  ))}
                </div>
              </div>

              <div
                style={{
                  display: 'flex',
                  gap: 8,
                  marginBottom: 20,
                }}
              >
                <button
                  type="button"
                  onClick={() => setGranularity('day')}
                  style={choiceStyle(granularity === 'day')}
                >
                  每日统计
                </button>

                <button
                  type="button"
                  onClick={() => setGranularity('week')}
                  style={choiceStyle(granularity === 'week')}
                >
                  每周统计
                </button>
              </div>

              {trends && (
                <>
                  <TrendChart items={trends.items} />

                  <div
                    style={{
                      display: 'flex',
                      flexWrap: 'wrap',
                      gap: 18,
                      marginTop: 16,
                      fontSize: 12,
                      color: '#6b7280',
                    }}
                  >
                    <Legend
                      color={colors.review}
                      label="复习次数"
                    />

                    <Legend
                      color={colors.newMistake}
                      label="新增错题"
                    />

                    <Legend
                      color={colors.masteredReview}
                      label="复习后标记已掌握"
                    />
                  </div>

                  <p
                    style={{
                      color: '#9ca3af',
                      fontSize: 12,
                      marginTop: 16,
                    }}
                  >
                    统计范围：{trends.start_date} 至 {trends.end_date}。
                    历史复习趋势从复习记录功能上线后开始积累。
                  </p>
                </>
              )}
            </div>
          </section>

          {/* 四、知识点掌握情况 */}
          <section style={{ marginBottom: 28 }}>
            <div style={panelStyle}>
              <SectionTitle
                title="知识点掌握情况"
                description="按照薄弱率查看需要重点加强的知识点。"
              />

              {overview.knowledge_points.length === 0 ? (
                <EmptyState text="暂无知识点统计数据，请先添加关联知识点的错题。" />
              ) : (
                <div>
                  {overview.knowledge_points.slice(0, 10).map((item) => (
                    <div
                      key={item.knowledge_point}
                      style={{
                        padding: '16px 0',
                        borderBottom: '1px solid #f0f0f0',
                      }}
                    >
                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          alignItems: 'center',
                          flexWrap: 'wrap',
                          gap: 10,
                          marginBottom: 10,
                        }}
                      >
                        <strong>
                          {item.knowledge_point}
                        </strong>

                        <span
                          style={{
                            fontSize: 13,
                            color:
                              item.status === 'weak'
                                ? '#dc2626'
                                : '#16a34a',
                          }}
                        >
                          {item.status === 'weak'
                            ? '需要加强'
                            : '已掌握'}
                        </span>
                      </div>

                      <div
                        style={{
                          height: 9,
                          borderRadius: 10,
                          overflow: 'hidden',
                          background: '#f3f4f6',
                          marginBottom: 9,
                        }}
                      >
                        <div
                          style={{
                            height: '100%',
                            width: `${item.weak_rate * 100}%`,
                            background: '#e58a58',
                            borderRadius: 10,
                          }}
                        />
                      </div>

                      <div
                        style={{
                          display: 'flex',
                          justifyContent: 'space-between',
                          fontSize: 12,
                          color: '#6b7280',
                          flexWrap: 'wrap',
                          gap: 8,
                        }}
                      >
                        <span>
                          错题总数：{item.total_mistakes}
                        </span>

                        <span>
                          未掌握：{item.unmastered_count}
                        </span>

                        <span>
                          薄弱率：{Math.round(item.weak_rate * 100)}%
                        </span>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </section>
        </>
      )}
    </div>
  );
}


// ==================== 通用组件 ====================

function SectionTitle({
  title,
  description,
}: {
  title: string;
  description: string;
}) {
  return (
    <div style={{ marginBottom: 20 }}>
      <h2
        style={{
          fontSize: 19,
          margin: 0,
          color: '#1f2937',
        }}
      >
        {title}
      </h2>

      <p
        style={{
          color: '#9ca3af',
          fontSize: 13,
          marginTop: 7,
          marginBottom: 0,
        }}
      >
        {description}
      </p>
    </div>
  );
}


function SummaryCard({
  label,
  value,
  description,
  color,
}: {
  label: string;
  value: number;
  description: string;
  color: string;
}) {
  return (
    <div
      style={{
        padding: 22,
        border: '1px solid #e5e7eb',
        borderRadius: 10,
        background: '#fff',
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
          margin: '12px 0 8px',
        }}
      >
        {value.toLocaleString()}
      </div>

      <div style={{ color: '#9ca3af', fontSize: 12 }}>
        {description}
      </div>
    </div>
  );
}


// ==================== 错题状态分布 ====================

function StatusDistribution({
  distribution,
}: {
  distribution: LearningOverview['status_distribution'];
}) {
  const total =
    distribution.pending +
    distribution.reviewing +
    distribution.mastered;

  const items = [
    {
      label: '待复习',
      value: distribution.pending,
      color: colors.pending,
    },
    {
      label: '复习中',
      value: distribution.reviewing,
      color: colors.reviewing,
    },
    {
      label: '已掌握',
      value: distribution.mastered,
      color: colors.mastered,
    },
  ];

  if (total === 0) {
    return <EmptyState text="目前还没有错题数据。" />;
  }

  return (
    <div>
      <div
        style={{
          display: 'flex',
          height: 18,
          overflow: 'hidden',
          borderRadius: 20,
          background: '#f3f4f6',
          gap: 2,
        }}
      >
        {items.map((item) => (
          <div
            key={item.label}
            title={`${item.label}：${item.value}`}
            style={{
              width: `${(item.value / total) * 100}%`,
              background: item.color,
            }}
          />
        ))}
      </div>

      <div
        style={{
          display: 'grid',
          gridTemplateColumns:
            'repeat(auto-fit, minmax(130px, 1fr))',
          gap: 16,
          marginTop: 24,
        }}
      >
        {items.map((item) => (
          <div key={item.label}>
            <Legend
              color={item.color}
              label={item.label}
            />

            <div
              style={{
                fontSize: 24,
                fontWeight: 700,
                marginTop: 9,
              }}
            >
              {item.value}
            </div>

            <div
              style={{
                color: '#9ca3af',
                fontSize: 12,
              }}
            >
              {((item.value / total) * 100).toFixed(1)}%
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}


// ==================== 趋势折线图 ====================

function TrendChart({
  items,
}: {
  items: LearningTrendItem[];
}) {
  const width = 760;
  const height = 280;

  const left = 48;
  const right = 20;
  const top = 20;
  const bottom = 42;

  const chartWidth = width - left - right;
  const chartHeight = height - top - bottom;

  if (items.length === 0) {
    return <EmptyState text="暂无趋势数据。" />;
  }

  const series = [
    {
      key: 'review_count',
      color: colors.review,
    },
    {
      key: 'new_mistake_count',
      color: colors.newMistake,
    },
    {
      key: 'mastered_review_count',
      color: colors.masteredReview,
    },
  ] as const;

  const maxValue = Math.max(
    1,
    ...items.flatMap((item) => [
      item.review_count,
      item.new_mistake_count,
      item.mastered_review_count,
    ])
  );

  const points = (
    key: typeof series[number]['key']
  ) => {
    return items.map((item, index) => {
      const x =
        left +
        (items.length === 1
          ? chartWidth / 2
          : (index / (items.length - 1)) * chartWidth);

      const y =
        top +
        chartHeight -
        (item[key] / maxValue) * chartHeight;

      return `${x},${y}`;
    });
  };

  const labelStep = Math.max(
    1,
    Math.ceil(items.length / 7)
  );

  const labelIndexes = items
    .map((_, index) => index)
    .filter(
      (index) =>
        index % labelStep === 0 ||
        index === items.length - 1
    );

  return (
    <div style={{ width: '100%', overflowX: 'auto' }}>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        width="100%"
        role="img"
        aria-label="学习趋势折线图"
        style={{
          minWidth: 320,
          display: 'block',
        }}
      >
        {/* 背景网格 */}
        {[0, 1, 2, 3].map((index) => {
          const y = top + (chartHeight / 3) * index;

          return (
            <g key={index}>
              <line
                x1={left}
                y1={y}
                x2={width - right}
                y2={y}
                stroke="#e5e7eb"
                strokeDasharray="4 4"
              />

              <text
                x={left - 10}
                y={y + 4}
                textAnchor="end"
                fontSize="11"
                fill="#9ca3af"
              >
                {Math.round(maxValue * (1 - index / 3))}
              </text>
            </g>
          );
        })}

        {/* 三条趋势线 */}
        {series.map((item) => (
          <polyline
            key={item.key}
            points={points(item.key).join(' ')}
            fill="none"
            stroke={item.color}
            strokeWidth="2.5"
            strokeLinejoin="round"
            strokeLinecap="round"
          />
        ))}

        {/* X 轴日期 */}
        {labelIndexes.map((index) => {
          const x =
            left +
            (items.length === 1
              ? chartWidth / 2
              : (index / (items.length - 1)) * chartWidth);

          const label = items[index].date.slice(5);

          return (
            <text
              key={items[index].date}
              x={x}
              y={height - 13}
              textAnchor="middle"
              fontSize="10"
              fill="#9ca3af"
            >
              {label}
            </text>
          );
        })}
      </svg>
    </div>
  );
}


// ==================== 其他组件 ====================

function Legend({
  color,
  label,
}: {
  color: string;
  label: string;
}) {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 7,
      }}
    >
      <span
        style={{
          width: 9,
          height: 9,
          borderRadius: '50%',
          background: color,
          flexShrink: 0,
        }}
      />

      <span>{label}</span>
    </div>
  );
}


function EmptyState({
  text,
}: {
  text: string;
}) {
  return (
    <div
      style={{
        padding: 30,
        textAlign: 'center',
        color: '#9ca3af',
        fontSize: 13,
      }}
    >
      {text}
    </div>
  );
}


// ==================== 样式 ====================

const panelStyle: React.CSSProperties = {
  background: '#fff',
  border: '1px solid #e5e7eb',
  borderRadius: 10,
  padding: 22,
};

const buttonStyle: React.CSSProperties = {
  padding: '9px 16px',
  border: '1px solid #d1d5db',
  borderRadius: 6,
  background: '#fff',
  cursor: 'pointer',
};

function choiceStyle(active: boolean): React.CSSProperties {
  return {
    padding: '7px 14px',
    borderRadius: 6,
    border: active
      ? '1px solid #2563eb'
      : '1px solid #d1d5db',
    background: active ? '#eff6ff' : '#fff',
    color: active ? '#2563eb' : '#4b5563',
    cursor: 'pointer',
  };
}

export default LearningAnalyticsView;
