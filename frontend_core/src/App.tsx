import { useState, useRef, useEffect, useCallback } from 'react';
import { Modal, message, Tooltip } from 'antd';
import {
  SendOutlined,
  DeleteOutlined,
  LineChartOutlined,
  HeartOutlined,
  LikeOutlined,
  LikeFilled,
  DislikeOutlined,
  DislikeFilled,
  ReloadOutlined,
  LoadingOutlined,
  BulbOutlined,
  LogoutOutlined,
  LoginOutlined,
} from '@ant-design/icons';
import axios from 'axios';
import type { CancelTokenSource } from 'axios';
import './App.css';
import ReactECharts from 'echarts-for-react';
import AuthModal from './components/AuthModal'
import React from 'react';


/* ============================================================
   全局配置
   ============================================================ */
axios.defaults.baseURL = '/';
axios.defaults.timeout = 20000;
axios.defaults.withCredentials = true;

const MIN_LEN = 5;
const MAX_LEN = 500;
const CAPTCHA_STORAGE_KEY    = 'dukkha_slide_verify_v1';
const CAPTCHA_STORAGE_TTL    = 30 * 60 * 1000;   // 30 分钟
const CAPTCHA_MESSAGE_KEY    = 'dukkha_slide_verify_msg';
const CAPTCHA_VERIFY_DEBOUNCE = 500;
const SESSION_ID = Math.random().toString(36).slice(2, 10); // 本次会话 ID（反馈用）


/* ============================================================
   类型定义
   ============================================================ */
type ReplyMode     = 'smart' | 'praise' | 'comfort';
type HistoryItem   = { role: 'user' | 'assistant'; content: string };
type AuthUser      = { id: number; email: string; username: string };
type FeedbackRating = 'like' | 'dislike' | 'regenerate' | null;

type Message = {
  id: number;
  text: string;
  guide?: string;
  keywords?: string[];
  isUser: boolean;
  time: string;
  emotion?: string;
  intensity?: number;
  sentimentLabel?: string;
  mode?: ReplyMode;
  isStreaming?: boolean;       // SSE 流式输出进行中
  feedback?: FeedbackRating;  // 用户反馈状态
};

type AnalysisPayload = {
  sentiment_category: number;
  sentiment_score: number;
  sentiment_label?: string;
  reply?: string;
  guide?: string;
  keywords?: string[];
  mode?: ReplyMode;
  originalText?: string;
};

/* ============================================================
   情绪 & 模式配置
   ============================================================ */
const EMOTION_CONFIG: Record<string, {
  gradient: string; label: string; glow: string; tagColor: string;
}> = {
  happy:   { gradient: 'linear-gradient(135deg,#fbbf24,#f59e0b)', label: '开心', glow: 'rgba(251,191,36,0.4)',  tagColor: '#f59e0b' },
  sad:     { gradient: 'linear-gradient(135deg,#60a5fa,#3b82f6)', label: '低落', glow: 'rgba(96,165,250,0.4)',  tagColor: '#3b82f6' },
  anxious: { gradient: 'linear-gradient(135deg,#a78bfa,#8b5cf6)', label: '焦虑', glow: 'rgba(167,139,250,0.4)', tagColor: '#8b5cf6' },
  angry:   { gradient: 'linear-gradient(135deg,#f87171,#ef4444)', label: '愤怒', glow: 'rgba(248,113,113,0.4)', tagColor: '#ef4444' },
  calm:    { gradient: 'linear-gradient(135deg,#34d399,#10b981)', label: '平静', glow: 'rgba(52,211,153,0.4)',  tagColor: '#10b981' },
  neutral: { gradient: 'linear-gradient(135deg,#9ca3af,#6b7280)', label: '中性', glow: 'rgba(156,163,175,0.4)', tagColor: '#6b7280' },
};

const MODES: Record<ReplyMode, { label: string; icon: React.ReactNode; prefix: string; desc: string }> = {
  smart:   { label: '智能分析', icon: <LineChartOutlined />, prefix: '✨', desc: '更懂情绪，也更会接住你' },
  praise:  { label: '暖心夸夸', icon: <LikeOutlined />,     prefix: '🌈', desc: '放大你的闪光点和价值感' },
  comfort: { label: '温柔安慰', icon: <HeartOutlined />,    prefix: '☁️', desc: '先陪着你，不急着给答案' },
};

/* ============================================================
   验证码辅助函数（旧版完整保留）
   ============================================================ */
const readCaptchaState = () => {
  try {
    const raw = localStorage.getItem(CAPTCHA_STORAGE_KEY);
    if (!raw) return false;
    const parsed = JSON.parse(raw) as { verified?: boolean; expiresAt?: number };
    if (!parsed?.verified || !parsed?.expiresAt || parsed.expiresAt <= Date.now()) {
      localStorage.removeItem(CAPTCHA_STORAGE_KEY);
      return false;
    }
    return true;
  } catch {
    return false;
  }
};

const persistCaptchaState = () => {
  try {
    localStorage.setItem(CAPTCHA_STORAGE_KEY, JSON.stringify({
      verified:  true,
      expiresAt: Date.now() + CAPTCHA_STORAGE_TTL,
    }));
  } catch {}
};

const clearCaptchaState = () => {
  try { localStorage.removeItem(CAPTCHA_STORAGE_KEY); } catch {}
};

const showCaptchaMessage = (type: 'success' | 'warning' | 'info', content: string, duration = 1.8) => {
  message.open({ key: CAPTCHA_MESSAGE_KEY, type, content, duration });
};

/* ============================================================
   情绪映射
   ============================================================ */
const mapEmotion = (cat: number, text: string): string => {
  if (cat === 1) return 'happy';
  if (cat === 2) {
    if (['焦虑','紧张','担心','压力','不安','失眠'].some(w => text.includes(w))) return 'anxious';
    if (['生气','愤怒','讨厌','烦','委屈','火大'].some(w => text.includes(w))) return 'angry';
    return 'sad';
  }
  if (cat === 4) return 'calm';
  return 'neutral';
};

const stripPrefix = (text: string) => text.replace(/^[✨🌈☁️]\s*/, '');

/* ============================================================
   滑块验证码（旧版完整保留，含 TTL 缓存 + debounce）
   ============================================================ */
const SlideCaptcha = ({
  onVerify,
  resetTrigger,
  verified,
}: {
  onVerify: (value: boolean) => void;
  resetTrigger: boolean;
  verified: boolean;
}) => {
  const [pos, setPos]   = useState(0);
  const [done, setDone] = useState(false);
  const ref             = useRef<HTMLDivElement>(null);
  const verifyAtRef     = useRef(0);

  useEffect(() => {
    const raf = window.requestAnimationFrame(() => {
      const max = ref.current ? Math.max(ref.current.clientWidth - 52, 0) : 0;
      if (verified) { setDone(true); setPos(max); return; }
      setDone(false); setPos(0);
    });
    return () => window.cancelAnimationFrame(raf);
  }, [resetTrigger, verified]);

  const finishVerify = useCallback(() => {
    const now = Date.now();
    if (done || now - verifyAtRef.current < CAPTCHA_VERIFY_DEBOUNCE) return;
    verifyAtRef.current = now;
    const max = ref.current ? Math.max(ref.current.clientWidth - 52, 0) : 0;
    setPos(max);
    setDone(true);
    onVerify(true);
    showCaptchaMessage('success', '验证成功，30 分钟内无需重复验证 ✨', 1.8);
  }, [done, onVerify]);

  const handleMove = useCallback((clientX: number) => {
    if (done || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const max  = rect.width - 52;
    const next = Math.max(0, Math.min(clientX - rect.left - 24, max));
    setPos(next);
    if (next >= max - 2) finishVerify();
  }, [done, finishVerify]);

  const resetIfNeeded = useCallback(() => { if (!done) setPos(0); }, [done]);

  const startDrag = () => {
    if (done) return;
    const onMove = (e: MouseEvent) => handleMove(e.clientX);
    const onUp   = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      resetIfNeeded();
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const startTouch = (e: React.TouchEvent) => {
    if (done) return;
    e.preventDefault();
    const onMove = (te: TouchEvent) => { if (te.touches[0]) handleMove(te.touches[0].clientX); };
    const onUp   = () => {
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onUp);
      resetIfNeeded();
    };
    window.addEventListener('touchmove', onMove, { passive: false });
    window.addEventListener('touchend', onUp);
  };

  return (
    <div className="captcha-wrap" ref={ref}>
      <div className="captcha-progress" style={{
        width: pos + 52,
        background: done
          ? 'linear-gradient(90deg,#10b981,#34d399)'
          : 'linear-gradient(90deg,rgba(99,102,241,0.15),rgba(99,102,241,0.3))',
      }} />
      <div
        className={`captcha-btn${done ? ' done' : ''}`}
        style={{ left: pos }}
        onMouseDown={startDrag}
        onTouchStart={startTouch}
      >
        {done ? '✓' : '>>'}
      </div>
      <span className={`captcha-label${done ? ' done' : ''}`}>
        {done ? '验证通过，当前设备 30 分钟内免验证' : '向右滑动完成验证'}
      </span>
    </div>
  );
};

/* ============================================================
   情绪能量球
   ============================================================ */
const EmotionBall = ({ emotion = 'neutral', intensity = 5 }: { emotion?: string; intensity?: number }) => {
  const config = EMOTION_CONFIG[emotion] || EMOTION_CONFIG.neutral;
  const size   = 58 + (intensity ?? 5) * 3;
  return (
    <div className="emotion-ball" style={{ width: size, height: size, background: config.gradient, boxShadow: `0 4px 20px ${config.glow}` }}>
      <span className="emotion-ball-label">{config.label}</span>
    </div>
  );
};

const EmotionTrend = ({ messages }: { messages: Message[] }) => {
  const data = messages
    .filter((m) => m.isUser && typeof m.intensity === 'number')
    .map((m, i) => [i + 1, m.intensity ?? 5]);

  if (data.length < 2) {
    return (
      <div className="trend-empty">
        <span className="trend-empty-icon">📈</span>
        多聊几句之后，这里会展示你的情绪变化趋势
      </div>
    );
  }

  const option = {
    grid: { left: 50, right: 20, bottom: 40, top: 30 },
    tooltip: {
      trigger: 'axis',
      formatter: (params: any) => {
        const p = Array.isArray(params) ? params[0] : params;
        const value = p.value[1];
        let level = '积极';
        if (value >= 7) level = '高危';
        else if (value >= 5) level = '中等';
        return `第 ${p.value[0]} 条消息<br/>强度：${p.value[1]}/10<br/>状态：${level}`;
      },
      backgroundColor: 'rgba(255,255,255,0.95)',
      borderColor: '#6366f1',
      borderWidth: 1,
      textStyle: { color: '#1e293b' },
    },
    xAxis: {
      type: 'value',
      name: '对话序号',
      nameTextStyle: { color: '#64748b', fontSize: 12 },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      axisLine: { lineStyle: { color: '#e2e8f0' } },
      splitLine: { show: false },
    },
    yAxis: {
      type: 'value',
      name: '情绪强度',
      min: 0,
      max: 10,
      nameTextStyle: { color: '#64748b', fontSize: 12 },
      axisLabel: { color: '#94a3b8', fontSize: 11 },
      splitLine: { lineStyle: { color: '#e2e8f0', type: 'dashed' } },
    },
    dataZoom: [
      { type: 'slider', bottom: 0, height: 14, start: 0, end: 100 },
      { type: 'inside' },
    ],
    series: [
      {
        type: 'line',
        smooth: true,
        showSymbol: true,
        symbolSize: 6,
        data,
        lineStyle: {
          width: 3,
          color: (params: any) => {
            const value = data[params.dataIndex]?.[1];
            if (value >= 7) return '#ef4444';
            if (value >= 5) return '#f59e0b';
            return '#10b981';
          }
        },
        areaStyle: {
          color: (params: any) => {
            const value = data[params.dataIndex]?.[1];
            if (value >= 7) return 'rgba(239,68,68,0.15)';
            if (value >= 5) return 'rgba(245,158,11,0.15)';
            return 'rgba(16,185,129,0.15)';
          }
        },
        itemStyle: {
          color: (params: any) => {
            const value = data[params.dataIndex]?.[1];
            if (value >= 7) return '#ef4444';
            if (value >= 5) return '#f59e0b';
            return '#10b981';
          },
          borderWidth: 1,
          borderColor: '#fff'
        },
      },
    ],
  };

  return (
    <div className="trend-echarts" style={{ width: '100%', height: 260 }}>
      <ReactECharts option={option} notMerge={true} lazyUpdate={true} style={{ height: '100%' }} />
      <div style={{ textAlign: 'center', fontSize: 11, color: '#94a3b8', marginTop: 4 }}>
        情绪强度变化趋势（共 {data.length} 条记录，可缩放/滑动查看）
      </div>
    </div>
  );
};



/* ============================================================
   分析卡片（旧版完整保留）
   ============================================================ */
const AnalysisCard = ({ data, originalText }: { data: AnalysisPayload | null; originalText?: string }) => {
  if (!data) return null;
  const emotion   = mapEmotion(data.sentiment_category, originalText || '');
  const config    = EMOTION_CONFIG[emotion] || EMOTION_CONFIG.neutral;
  const catMap: Record<number, string> = { 1:'正向', 2:'负向', 3:'复杂混合', 4:'中性', 5:'不相关' };
  return (
    <div className="glass-card analysis-card" style={{ borderLeftColor: config.tagColor }}>
      <div className="analysis-header">
        <div className="analysis-info">
          <div className="analysis-title">📋 情绪分析结果</div>
          <div className="analysis-tags">
            <span className="emotion-tag" style={{ background: config.gradient, boxShadow: `0 2px 8px ${config.glow}` }}>
              {catMap[data.sentiment_category] ?? '未知'}
            </span>
            <span className="score-text">强度 {Number(data.sentiment_score || 0).toFixed(1)}/10</span>
          </div>
          {Array.isArray(data.keywords) && data.keywords.length > 0 && (
            <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginTop:6 }}>
              {data.keywords.map((kw, i) => <span key={i} className="keyword-tag">{kw}</span>)}
            </div>
          )}
        </div>
        <EmotionBall emotion={emotion} intensity={data.sentiment_score} />
      </div>
      {data.guide && (
        <>
          <div className="analysis-divider" />
          <div className="guide-row">
            <BulbOutlined className="guide-icon" style={{ color:'#f59e0b' }} />
            <span className="guide-text">{data.guide}</span>
          </div>
        </>
      )}
    </div>
  );
};

/* ============================================================
   反馈按钮组件（新增：鼠标悬停 AI 消息时显示）
   ============================================================ */
const FeedbackButtons = ({
  msgId, userInput, aiReply, mode, sentimentScore, sentimentLabel, onFeedback,
}: {
  msgId: number;
  userInput: string;
  aiReply: string;
  mode?: ReplyMode;
  sentimentScore?: number;
  sentimentLabel?: string;
  onFeedback: (msgId: number, rating: FeedbackRating) => void;
}) => {
  const [submitted,  setSubmitted]  = useState<FeedbackRating>(null);
  const [submitting, setSubmitting] = useState(false);

  // ✅ 自动消失：3 秒后反馈按钮自动隐藏
  useEffect(() => {
    if (submitted) {
      const timer = setTimeout(() => {
        setSubmitted(null);
      }, 3000);
      return () => clearTimeout(timer);
    }
  }, [submitted]);

  const handleClick = async (rating: FeedbackRating) => {
    if (submitted || submitting) return;
    setSubmitting(true);
    try {
      await axios.post('/api/feedback', {
        user_input:      userInput,
        ai_reply:        aiReply,
        rating,
        emotion_mode:    mode || 'smart',
        sentiment_score: sentimentScore,
        sentiment_label: sentimentLabel,
        session_id:      SESSION_ID,
      });
      setSubmitted(rating);
      onFeedback(msgId, rating);
      message.success(rating === 'like' ? '谢谢你的反馈 💖' : '反馈已记录，我会变得更好 🙏', 1.5);
    } catch {
      message.error('反馈提交失败，请稍后重试', 2);
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="feedback-btns">
      <Tooltip title="有帮助">
        <button className={`feedback-btn like${submitted==='like'?' active':''}`} onClick={()=>handleClick('like')} disabled={!!submitted||submitting} type="button">
          {submitted === 'like' ? <LikeFilled /> : <LikeOutlined />}
        </button>
      </Tooltip>
      <Tooltip title="不太对">
        <button className={`feedback-btn dislike${submitted==='dislike'?' active':''}`} onClick={()=>handleClick('dislike')} disabled={!!submitted||submitting} type="button">
          {submitted === 'dislike' ? <DislikeFilled /> : <DislikeOutlined />}
        </button>
      </Tooltip>
      <Tooltip title="重新生成">
        <button className="feedback-btn regen" onClick={()=>handleClick('regenerate')} disabled={!!submitted||submitting} type="button">
          <ReloadOutlined />
        </button>
      </Tooltip>
    </div>
  );
};

/* ============================================================
   主应用
   ============================================================ */
export default function App() {
  const [autoScroll, setAutoScroll] = useState(true);
  const [showTrend, setShowTrend] = useState(false);
  const path = window.location.pathname;
  if (path === '/privacy') return <PrivacyPage />;
  if (path === '/terms') return <TermsPage />;
  if (path === '/disclaimer') return <DisclaimerPage />;
  // ── 认证状态 ──────────────────────────────────────────────
  const [authUser,    setAuthUser]    = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [showAuth,    setShowAuth]    = useState(false);
  // ✅ v2.6 新增：页面初始化时自动拉取当前用户信息
  useEffect(() => {
    const loadCurrentUser = async () => {
      try {
        const res = await axios.get('/api/auth/me', { withCredentials: true });
        if (res.data?.code === 200 && res.data?.data) {
          setAuthUser(res.data.data);
        } else {
          setAuthUser(null);
        }
      } catch (err) {
        setAuthUser(null);
      } finally {
        setAuthLoading(false);
      }
    };

    loadCurrentUser();
  }, []);

  // ✅ GitHub OAuth 登录状态同步（桌面端弹窗）
useEffect(() => {
  const handleGithubMessage = (event: MessageEvent) => {
    // 安全校验：只接受同源消息
    if (event.origin !== window.location.origin) return;
    if (event.data?.type !== 'github_login_success') return;

    axios.get('/api/auth/me', { withCredentials: true })
      .then(res => {
        if (res.data?.code === 200 && res.data?.data) {
          setAuthUser(res.data.data);
          message.success('GitHub 登录成功 🎉');
        }
      })
      .catch(() => {});
  };

  window.addEventListener('message', handleGithubMessage);
  return () => window.removeEventListener('message', handleGithubMessage);
}, []);

// ✅ GitHub OAuth 登录状态同步（手机端整页跳转回首页）
useEffect(() => {
  const params = new URLSearchParams(window.location.search);
  if (params.get('github_login') !== '1') return;

  // 清理 URL，避免刷新时重复触发
  window.history.replaceState({}, document.title, window.location.pathname);

  axios.get('/api/auth/me', { withCredentials: true })
    .then(res => {
      if (res.data?.code === 200 && res.data?.data) {
        setAuthUser(res.data.data);
        message.success('GitHub 登录成功 🎉');
      }
    })
    .catch(() => {});
}, []);


  // ── 聊天状态 ──────────────────────────────────────────────
  const [messages,  setMessages]  = useState<Message[]>([]);
  const [input,     setInput]     = useState('');
  const [loading,   setLoading]   = useState(false);
  const [verified,  setVerified]  = useState(false);
  const [resetCap,  setResetCap]  = useState(false);
  const [mode,      setMode]      = useState<ReplyMode>('smart');
  const [analysis,  setAnalysis]  = useState<AnalysisPayload | null>(null);
  // 记录每条 AI 消息对应的用户输入（反馈接口需要）
  const [msgUserInput, setMsgUserInput] = useState<Record<number, string>>({});

  const bottomRef   = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const cancelRef   = useRef<CancelTokenSource | null>(null); // 保留，用于组件卸载清理
  const abortRef    = useRef<AbortController | null>(null);   // SSE 取消

  /* ── 验证码相关 ─────────────────────────────────────────── */
  const handleCaptchaVerify = useCallback((value: boolean) => {
    setVerified(value);
    if (value) persistCaptchaState(); else clearCaptchaState();
  }, []);

  // 初始化：读取本地缓存的验证状态
  useEffect(() => { setVerified(readCaptchaState()); }, []);

  // 定时检测验证码是否过期（15 秒轮询）
  useEffect(() => {
    if (!verified) return;
    const timer = window.setInterval(() => {
      if (!readCaptchaState()) {
        setVerified(false);
        setResetCap(p => !p);
        showCaptchaMessage('info', '滑块验证已过期，请重新验证', 2);
      }
    }, 15000);
    return () => window.clearInterval(timer);
  }, [verified]);

  /* ── 自动检查登录状态（Cookie）────────────────────────────── */
  useEffect(() => {
    (async () => {
      try {
        const res = await axios.get('/api/auth/me');
        if (res.data.code === 200) setAuthUser(res.data.data);
      } catch {} finally { setAuthLoading(false); }
    })();
  }, []);

/* ── 登录后拉取云端历史 ─────────────────────────────────── */
  useEffect(() => {
    if (!authUser) return;
    (async () => {
      try {
        const res = await axios.get('/api/history');
        if (res.data.code === 200 && Array.isArray(res.data.data.messages)) {
        // ✅ 限制最多保留 500 条，防止接口分页或旧代码只传 60
        const serverMsgs: Message[] = res.data.data.messages.slice(-500);
        if (serverMsgs.length > 0) {
          setMessages(serverMsgs);
          setMode(res.data.data.mode || 'smart');
          message.info(`已恢复 ${serverMsgs.length} 条历史记录 📚`, 2);
        }
      }
    } catch {
      try {
        // ✅ 本地恢复同样限制为 500 条
        const local = localStorage.getItem(`dukkha_${authUser.id}`);
        if (local) {
          const p = JSON.parse(local);
          if (Array.isArray(p)) setMessages(p.slice(-500));
        }
      } catch {}
    }
    })();
  }, [authUser]);

  /* ── 消息变化：滚动 + 本地缓存 + 云端同步 ──────────────── */
  useEffect(() => {
    // ✅ 改成这样：受 autoScroll 控制，如果你往上滑了，就不执行这句滚动
    if (autoScroll) {
      bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
    
    // 👇 下面你的缓存和接口代码，一字不改！！完美保留！！
    if (messages.length === 0) return;
    const cacheKey = authUser ? `dukkha_${authUser.id}` : 'dukkha_guest';
    try { localStorage.setItem(cacheKey, JSON.stringify(messages.slice(-500))); } catch {}
    if (!authUser) return;
    const timer = window.setTimeout(async () => {
      try { await axios.post('/api/history', { messages: messages.slice(-500), mode }); } catch {}
    }, 800);
    return () => window.clearTimeout(timer);
  }, [messages, authUser, mode]); 


  /* ── 自适应输入框高度 ───────────────────────────────────── */
  useEffect(() => {
    const ta = textareaRef.current; if (!ta) return;
    ta.style.height = 'auto';
    ta.style.height = `${Math.min(ta.scrollHeight, 160)}px`;
  }, [input]);

  /* ── 清理 ────────────────────────────────────────────────── */
  useEffect(() => () => {
    cancelRef.current?.cancel('unmount');
    abortRef.current?.abort();
  }, []);

  /* ── 构建历史 ────────────────────────────────────────────── */
  const buildHistory = (): HistoryItem[] =>
    messages.slice(-6).map(m => ({
      role:    m.isUser ? 'user' : 'assistant',
      content: m.isUser ? m.text : stripPrefix(m.text),
    }));

  /* ── 登出 ─────────────────────────────────────────────────── */
  const handleLogout = async () => {
    Modal.confirm({
      title: '确认退出登录？', content: '退出后云端记录仍会保留，下次登录会自动恢复。',
      okText: '退出', cancelText: '取消', okButtonProps: { danger: true },
      onOk: async () => {
        await axios.post('/api/auth/logout').catch(() => {});
        setAuthUser(null); setMessages([]); setAnalysis(null);
        message.success('已退出登录', 2);
      },
    });
  };

  /* ============================================================
     核心发送逻辑 —— 修复SSE流式（打字机效果 + 乐观UI）
     ============================================================ */
  const sendMessage = async () => {
    if (loading) return;
  
  // ✅ 检查游客额度
  if (!authUser) {
    const guestCountStr = localStorage.getItem('guest_count');
    const guestCount = guestCountStr ? parseInt(guestCountStr) : 0;
    const GUEST_LIMIT = 6; 
    if (guestCount >= GUEST_LIMIT) {
      message.warning('游客额度已用尽，请登录继续使用');
      setShowAuth(true);
      return;
    }
  }
    const text = input.trim();
    if (text.length < MIN_LEN) { message.warning(`至少输入 ${MIN_LEN} 个字哦～`, 2); return; }
    if (!verified) { showCaptchaMessage('warning', '请先完成滑块验证哦～', 2); return; }

    // 取消上一次未完成的 SSE 流
    abortRef.current?.abort();
    const abort = new AbortController();
    abortRef.current = abort;

    const now = new Date().toLocaleTimeString('zh-CN', { hour:'2-digit', minute:'2-digit', hour12:false });
    const prefix = MODES[mode].prefix;

    // ── 乐观UI：立刻显示用户消息 ──
    const userMsg: Message = { id: Date.now(), text, isUser: true, time: now, emotion: 'neutral', intensity: 5 };
    const aiMsgId = Date.now() + 1;
    const aiMsgPlaceholder: Message = { 
      id: aiMsgId, 
      text: '', 
      isUser: false, 
      time: now, 
      emotion: 'neutral', 
      intensity: 5, 
      mode, 
      isStreaming: true 
    };

    setMessages(prev => [...prev, userMsg, aiMsgPlaceholder]);
    setMsgUserInput(prev => ({ ...prev, [aiMsgId]: text }));
    setInput('');
    setLoading(true);

    try {
      // 发起SSE请求
      const res = await fetch('/api/emo_analysis_stream', {
        method:  'POST',
        headers: {
            'Content-Type': 'application/json',
            'Accept': 'text/event-stream',
            'Cache-Control': 'no-cache',
            'Connection': 'keep-alive'
        },   
        body: JSON.stringify({ text, mode, history: buildHistory() }),
        signal:  abort.signal,
        credentials: 'include',
      });

      // ── 后端 SSE 不可用时降级到普通接口 ──
      if (!res.ok || !res.body) {
        throw new Error(`HTTP ${res.status}`);
      }

      const reader  = res.body.getReader();
      const decoder = new TextDecoder('utf-8');
      let   buffer  = '';
      let   fullReply = '';
      let   analysisData: any = null;

      // 循环读取SSE流
      while (true) {
        const { done, value } = await reader.read();
        
        // 流结束
        if (done) {
          // 确保最后更新流式状态为false
          setMessages(prev => prev.map(m => 
            m.id === aiMsgId ? { ...m, isStreaming: false } : m
          ));
          break;
        }

        // 解码并处理数据
        buffer += decoder.decode(value, { stream: true });
        // 按行分割（SSE每行以\n分隔）
        const lines = buffer.split(/\r?\n/);
        buffer = lines.pop() || '';

        // 处理每一行SSE消息
        for (const line of lines) {
          if (!line || !line.startsWith('data: ')) continue;
          
          const jsonStr = line.slice(6).trim();
          if (!jsonStr) continue;

          try {
            const event = JSON.parse(jsonStr);
            
                      if (event.type === 'thinking' && event.content) {
            setMessages(prev => prev.map(m => 
              m.id === aiMsgId ? { 
                ...m, 
                text: event.content,
                isStreaming: true 
              } : m
            ));
          }
          else if (event.type === 'token' && event.content) {
            fullReply += event.content;
            setMessages(prev => prev.map(m => 
              m.id === aiMsgId ? { 
                ...m, 
                text: `${prefix} ${fullReply}`, 
                isStreaming: true 
              } : m
            ));
            await new Promise(r => setTimeout(r, 0));
          } 
            // 2. 处理分析数据
            else if (event.type === 'analysis' && event.data) {
              analysisData = event.data;
              setAnalysis({ ...event.data, originalText: text });
              // 更新用户消息的情绪信息
              setMessages(prev => prev.map(m => 
                m.id === userMsg.id ? { 
                  ...m, 
                  emotion: mapEmotion(event.data.sentiment_category, text),
                  intensity: Math.min(10, Math.max(1, Math.round(event.data.sentiment_score || 5)))
                } : m
              ));
            } 
            // 3. 处理结束信号
            else if (event.type === 'done') {
              // 最终更新AI消息
              const finalText = fullReply ? `${prefix} ${fullReply}` : `${prefix} 我在这里，慢慢说。`;
              const emotion   = analysisData ? mapEmotion(analysisData.sentiment_category, text) : 'neutral';
              const intensity = analysisData ? Math.min(10, Math.max(1, Math.round(analysisData.sentiment_score || 5))) : 5;
              
              setMessages(prev => prev.map(m => 
                m.id === aiMsgId ? { 
                  ...m, 
                  text: finalText,
                  guide: analysisData?.guide,
                  keywords: analysisData?.keywords || [],
                  emotion: emotion,
                  intensity: intensity,
                  sentimentLabel: analysisData?.sentiment_label,
                  isStreaming: false // 结束流式
                } : m
              ));
            } 
            // 4. 处理错误
            else if (event.type === 'error') {
              throw new Error(event.msg || '服务错误');
            }
                    } catch (e: any) {
            if (e.message && e.message.includes('试用额度已达上限')) {
              message.error('游客额度已用尽，请登录继续使用');
              setShowAuth(true);
              setMessages(prev => prev.filter(m => m.id !== aiMsgId));
              reader.cancel();
              abort.abort();
              setLoading(false);
              return;
            }
            console.warn('解析SSE消息失败:', e);
            continue;
          }

        }
      }
    } catch (err: any) {
      if (err.name === 'AbortError') return;

      // ── SSE 接口不存在，自动降级到普通接口 ──
      try {
        cancelRef.current = axios.CancelToken.source();
        const response = await axios.post(
          '/api/emo_analysis',
          { text, mode, history: buildHistory() },
          { cancelToken: cancelRef.current.token },
        );
        const result = response.data;
        if (result.code !== 200) throw new Error(result.msg || '分析失败');
        const d       = result.data || {};
        const emotion   = mapEmotion(d.sentiment_category, text);
        const intensity = Math.min(10, Math.max(1, Math.round(d.sentiment_score || 5)));
        const aiText    = d.reply ? `${prefix} ${d.reply}` : `${prefix} 我在这里，慢慢说。`;
        setAnalysis({ ...d, originalText: text });
        setMessages(prev => {
          const upd = prev.map(m => m.id === userMsg.id ? { ...m, emotion, intensity } : m);
          return upd.map(m =>
            m.id === aiMsgId
              ? { ...m, text: aiText, guide: d.guide, keywords: d.keywords||[], emotion, intensity, sentimentLabel: d.sentiment_label, isStreaming: false }
              : m
          );
        });
      } catch (fallbackErr: any) {
        if (axios.isCancel(fallbackErr)) return;
  
  // ✅ 检查是否是额度超限错误
        const errMsg = fallbackErr.response?.data?.msg || fallbackErr.message || '请稍后再试';
        if (errMsg && errMsg.includes('试用额度已达上限')) {
            message.error('游客额度已用尽，请登录继续使用', 3);
            setShowAuth(true);
            setMessages(prev => prev.filter(m => m.id !== aiMsgId)); // 删掉那条失败的消息
            return;
            }
  
            message.error(errMsg, 3);
            setMessages(prev => prev.map(m =>
                m.id === aiMsgId
                    ? { ...m, text: `${prefix} 我听见你了，虽然这次没有顺利分析，但我还在这里陪着你。`, isStreaming: false }
                    : m
            ));
      }
    } finally {
      setLoading(false);
      abortRef.current = null;
      cancelRef.current = null;
    }
  };

  const handleTextareaKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
  };

  /* ── 反馈回调 ────────────────────────────────────────────── */
  const handleFeedback = (msgId: number, rating: FeedbackRating) => {
    setMessages(prev => prev.map(m => m.id === msgId ? { ...m, feedback: rating } : m));
  };

  /* ── 清空对话 ────────────────────────────────────────────── */
  const clearAll = () => {
    Modal.confirm({
      title: '确认清空聊天记录？',
      content: authUser ? '本地和云端记录都会一起删除，操作后不可恢复。' : '本地聊天记录会被清空。',
      okText: '确认清空', cancelText: '再想想',
      okButtonProps: { danger: true },
      onOk: async () => {
        if (authUser) await axios.delete('/api/history').catch(() => {});
        const cacheKey = authUser ? `dukkha_${authUser.id}` : 'dukkha_guest';
        localStorage.removeItem(cacheKey);
        setMessages([]); setAnalysis(null); setMsgUserInput({});
        message.success('聊天记录已清空 ✨', 2);
      },
    });
  };

  const canSend = !loading && verified && input.trim().length >= MIN_LEN;

  /* ── 首屏加载 ────────────────────────────────────────────── */
  if (authLoading) {
    return (
      <>
        <div className="page-bg" />
        <div className="auth-init-loader">
          <div className="auth-init-spinner" />
          <span>正在连接...</span>
        </div>
      </>
    );
  }

  /* ============================================================
     渲染
     ============================================================ */
  return (
    <>
      <div className="page-bg" />
      <div className="bg-blob bg-blob-1" />
      <div className="bg-blob bg-blob-2" />
      <div className="bg-blob bg-blob-3" />

      <AuthModal
  open={showAuth}
  onClose={() => setShowAuth(false)}
  onSuccess={(userData) => {
    setAuthUser(userData)
    setShowAuth(false)
    message.success(`欢迎，${userData.username || userData.email} 🎉`);
  }}
/>

      <div className="app-layout">
        <div className="app-content">

          {/* ===== 顶部标题卡片 ===== */}
          <div className="glass-card header-card">
            <div className="top-bar" />
            <div className="user-bar">
              {authUser ? (
                <div className="user-info">
                  <div className="user-avatar">{(authUser.username || authUser.email)[0].toUpperCase()}</div>
                  <span className="user-name">{authUser.username || authUser.email}</span>
                  <Tooltip title="退出登录">
                    <button className="logout-btn" onClick={handleLogout} type="button"><LogoutOutlined /></button>
                  </Tooltip>
                </div>
              ) : (
                <button className="login-btn" onClick={()=>setShowAuth(true)} type="button">
                  <LoginOutlined />&nbsp;登录 / 注册
                </button>
              )}
            </div>

            <div className="header-title">
              <span className="title-icon">💗</span>
              温柔情绪陪伴站
            </div>
            <div className="header-subtitle">
              {authUser ? `${authUser.username}，今天也可以把心事放心交给我。` : '你说一句，我就认真接住一句。'}
            </div>

            <div className="mode-group">
              {(Object.entries(MODES) as Array<[ReplyMode, typeof MODES[ReplyMode]]>).map(([key, val]) => (
                <Tooltip key={key} title={val.desc} placement="bottom">
                  <button className={`mode-btn${mode===key?' active':''}`} onClick={()=>setMode(key)} type="button">
                    {val.icon}&nbsp;{val.label}
                  </button>
                </Tooltip>
              ))}
            </div>
            <div className="mode-desc">{MODES[mode].desc}</div>
          {/* ✅ 非医疗免责声明 Banner */}
          <div style={{
            marginTop:10, padding:'6px 12px',
            background:'rgba(239,68,68,0.07)',
            border:'1px solid rgba(239,68,68,0.15)',
            borderRadius:8,
            fontSize:11, color:'#b91c1c',
            lineHeight:1.7, textAlign:'center'
          }}>
            ⚠️ 本系统为 AI 情绪陪伴工具，不替代专业心理咨询或医疗诊断。
            遇到心理危机请拨打全国心理援助热线{' '}
            <a href="tel:4001619995" style={{ color:'#b91c1c', fontWeight:700 }}>400-161-9995</a>
          </div>


            {!authUser && (
              <div className="guest-banner">
                <span>游客聊天会先保存在本地。</span>
                <span className="guest-login-link" onClick={()=>setShowAuth(true)}>登录后永久云端保存</span>
              </div>
            )}
          </div>

          {/* ===== 分析结果卡片 ===== */}
          <AnalysisCard data={analysis} originalText={analysis?.originalText} />

          {/* ===== 聊天区域 ===== */}
          <div className="glass-card chat-card">
            <div 
              className="chat-body" 
              onScroll={(e) => {
                const target = e.currentTarget;
                const isAtBottom = target.scrollHeight - target.scrollTop - target.clientHeight < 80;
                setAutoScroll(isAtBottom);
            }}
          >

              {messages.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-icon">🫶</span>
                  <span className="empty-text">
                    {authUser ? `${authUser.username}，今天心情怎么样？` : '还没有聊天记录，说说今天的心情吧～'}
                  </span>
                </div>
              ) : (
                <>
                  {messages.map(m => {
                    const cfg = EMOTION_CONFIG[m.emotion || 'neutral'] || EMOTION_CONFIG.neutral;
                    return (
                      <div key={m.id} className={`message-wrap ${m.isUser ? 'user' : 'ai'}`}>
                        {/* 用户消息：情绪标签 */}
                        {m.isUser && m.emotion && m.emotion !== 'neutral' && (
                          <div className="bubble-tag">
                            <span className="emotion-tag" style={{ background: cfg.gradient, boxShadow: `0 2px 8px ${cfg.glow}`, fontSize: 11 }}>
                              {cfg.label}{m.intensity ? ` · ${m.intensity}/10` : ''}
                            </span>
                          </div>
                        )}
                        {/* AI 消息：sentiment label 标签 */}
                        {!m.isUser && m.sentimentLabel && (
                          <div className="bubble-tag">
                            <span className="keyword-tag">{m.sentimentLabel}</span>
                          </div>
                        )}

                        {/* 气泡主体（流式时加 streaming 类名 + 光标） */}
                        <div className={`bubble ${m.isUser?'user':'ai'}${m.isStreaming?' streaming':''}`}>
                          {/* 空文本时显示打字三点动画 */}
                          {m.isStreaming && !m.text ? (
                            <div className="typing-dots">
                              <div className="typing-dot"/><div className="typing-dot"/><div className="typing-dot"/>
                            </div>
                          ) : m.text}
                          {/* 流式光标 */}
                          {m.isStreaming && m.text && <span className="stream-cursor">|</span>}
                        </div>

                        {/* AI 消息：keywords 标签 */}
                        {!m.isUser && m.keywords && m.keywords.length > 0 && (
                          <div style={{ display:'flex', gap:6, flexWrap:'wrap', marginTop:6 }}>
                            {m.keywords.map((kw, i) => <span key={i} className="keyword-tag">{kw}</span>)}
                          </div>
                        )}

                        <div className="bubble-time">
                          {m.time}{m.mode && !m.isUser ? ` · ${MODES[m.mode]?.label}` : ''}
                        </div>

                        {/* 反馈按钮（仅 AI 消息 + 流式结束后显示） */}
                        {!m.isUser && !m.isStreaming && m.text && (
                          <FeedbackButtons
                            msgId={m.id}
                            userInput={msgUserInput[m.id] || ''}
                            aiReply={m.text}
                            mode={m.mode}
                            sentimentScore={m.intensity}
                            sentimentLabel={m.sentimentLabel}
                            onFeedback={handleFeedback}
                          />
                        )}
                      </div>
                    );
                  })}
                  <div ref={bottomRef} />
                </>
              )}
            </div>
          </div>

            {/* ===== 情绪趋势图（可折叠） ===== */}
          <div className="glass-card trend-card">
            <div 
              className="trend-title" 
              style={{ cursor: 'pointer', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}
              onClick={() => setShowTrend(!showTrend)}
            >
              <span><LineChartOutlined /> 情绪趋势</span>
              <span style={{ fontSize: 13, color: '#6366f1', fontWeight: 'normal' }}>
                {showTrend ? '收起 ▲' : '展开 ▼'}
              </span>
            </div>
            {showTrend && <EmotionTrend messages={messages} />}
          </div>


          {/* ===== 输入区域 ===== */}
          <div className="glass-card input-card">
            {/* ✅ 滑块验证：仅在未验证时显示，验证后自动隐藏 */}
            {!verified && (
              <div className="captcha-safe-wrapper">
                <SlideCaptcha onVerify={handleCaptchaVerify} resetTrigger={resetCap} verified={verified} />
              </div>
            )}


            <textarea
              ref={textareaRef}
              className="chat-textarea"
              value={input}
              onChange={e => setInput(e.target.value.slice(0, MAX_LEN))}
              onKeyDown={handleTextareaKeyDown}
              placeholder={`今天心情怎么样？（至少 ${MIN_LEN} 字，Shift+Enter 换行）`}
              disabled={loading}
              maxLength={MAX_LEN}
              rows={3}
            />

            <div className={`char-count${input.length > MAX_LEN * 0.9 ? ' warn' : ''}${input.length >= MAX_LEN ? ' over' : ''}`}>
              {input.length} / {MAX_LEN}
            </div>

                        <div style={{ display: 'flex', gap: 8, justifyContent: 'space-between' }}>
  <Tooltip title="清空聊天记录">
    <button
      className="clear-btn-circle"
      onClick={clearAll}
      type="button"
      style={{
        width: 48,
        height: 48,
        borderRadius: '50%',
        border: 'none',
        background: '#ef4444',
        color: '#fff',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 18,
        transition: 'all 0.3s',
        marginTop: -8
      }}
    >
      <DeleteOutlined />
    </button>
  </Tooltip>

  <Tooltip title={loading ? 'AI 正在回应...' : '发送消息'}>
    <button
      className="send-btn-circle"
      onClick={sendMessage}
      disabled={!canSend}
      type="button"
      style={{
        width: 56,
        height: 56,
        borderRadius: '50%',
        border: 'none',
        background: '#6366f1',
        color: '#fff',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        fontSize: 22,
        transition: 'all 0.3s',
        opacity: !canSend ? 0.5 : 1,
        marginTop: -8,
        marginRight: 16
      }}
    >
      {loading ? <LoadingOutlined /> : <SendOutlined />}
    </button>
  </Tooltip>
</div>



            {authUser && messages.length > 0 && <div className="sync-hint">☁️ 已自动同步到云端</div>}
          </div>
          {/* ✅ 页脚版权 / 政策链接 */}
          <div style={{
            textAlign:'center', fontSize:11, color:'rgba(0,0,0,0.55)',
            padding:'24px 0', lineHeight:2, marginTop:40
          }}>
            媛心烨语 · AI 情绪陪伴系统 © 2025<br/>
            <a href="/privacy" style={{ color:'#6366f1', marginRight:12 }}>隐私政策</a>
            <a href="/terms" style={{ color:'#6366f1', marginRight:12 }}>用户协议</a>
            <a href="/disclaimer" style={{ color:'#6366f1' }}>免责声明</a>
          </div>

        </div>
      </div>
    </>
  );
}
/* ============================================================
   ✅ 合规页面组件（隐私政策 / 用户协议 / 免责声明）
   ============================================================ */

function PrivacyPage() {
  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '40px 24px', lineHeight: 1.8, background: '#fff', minHeight: '100vh', fontSize: 14, color: '#333' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 24 }}>媛心烨语 · 隐私政策</h1>
      
      <div style={{ marginBottom: 32, color: '#666' }}>
        <p><strong>生效日期：</strong>2025年1月1日</p>
        <p><strong>最后更新：</strong>2025年4月</p>
        <p><strong>适用版本：</strong>媛心烨语 v3.x</p>
      </div>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>一、总则</h2>
      <p>媛心烨语（以下简称"本产品"或"我们"）是面向大学生群体的 AI 情绪陪伴系统，由参赛团队开发，用于第十九届中国大学生计算机设计大赛。</p>
      <p>我们深知心理健康数据的高度敏感性，因此将隐私保护置于产品设计的核心位置。本政策说明我们收集哪些数据、如何使用、如何保护以及你拥有哪些权利。</p>
      <p><strong style={{ color: '#ef4444' }}>如果你不同意本政策，请不要注册或使用本产品。</strong></p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>二、我们收集的数据</h2>
      
      <h3 style={{ fontSize: 16, fontWeight: 600, marginTop: 20, marginBottom: 12 }}>2.1 你主动提供的数据</h3>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 20 }}>
        <thead>
          <tr style={{ background: '#f5f5f5', borderBottom: '2px solid #ddd' }}>
            <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>数据类型</th>
            <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>具体内容</th>
            <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>用途</th>
          </tr>
        </thead>
        <tbody>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}>账号信息</td>
            <td style={{ padding: 12 }}>邮箱地址、用户名、加密密码</td>
            <td style={{ padding: 12 }}>账号识别与登录验证</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}>对话内容</td>
            <td style={{ padding: 12 }}>你发送的文字消息</td>
            <td style={{ padding: 12 }}>情绪分析与 AI 回复生成</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}>反馈数据</td>
            <td style={{ padding: 12 }}>点赞/踩/重新生成操作</td>
            <td style={{ padding: 12 }}>改善回复质量（RLHF）</td>
          </tr>
        </tbody>
      </table>

      <h3 style={{ fontSize: 16, fontWeight: 600, marginTop: 20, marginBottom: 12 }}>2.2 系统自动生成的数据</h3>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 20 }}>
        <thead>
          <tr style={{ background: '#f5f5f5', borderBottom: '2px solid #ddd' }}>
            <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>数据类型</th>
            <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>具体内容</th>
            <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>用途</th>
          </tr>
        </thead>
        <tbody>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}>情绪记录</td>
            <td style={{ padding: 12 }}>情绪类别、强度评分、关键词</td>
            <td style={{ padding: 12 }}>情绪趋势分析</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}>用户画像</td>
            <td style={{ padding: 12 }}>压力关键词、情绪均值、危机计数</td>
            <td style={{ padding: 12 }}>个性化陪伴优化</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}>深度画像</td>
            <td style={{ padding: 12 }}>交流风格、支持偏好（推测型）</td>
            <td style={{ padding: 12 }}>辅助 AI 理解你的偏好</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}>访问日志</td>
            <td style={{ padding: 12 }}>IP 地址、请求时间（脱敏处理）</td>
            <td style={{ padding: 12 }}>安全防护与限流</td>
          </tr>
        </tbody>
      </table>

      <h3 style={{ fontSize: 16, fontWeight: 600, marginTop: 20, marginBottom: 12 }}>2.3 第三方登录数据</h3>
      <p>当你选择 GitHub 授权登录时，我们仅获取 GitHub 的用户 ID、用户名和邮箱地址，不读取你的代码仓库、commit 记录或其他任何 GitHub 数据。</p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>三、数据使用方式</h2>
      <p><strong>我们使用你的数据只为以下目的：</strong></p>
      <ol style={{ marginLeft: 20, marginBottom: 16 }}>
        <li><strong>提供服务</strong>：分析你的情绪状态，生成个性化陪伴回复</li>
        <li><strong>改善体验</strong>：根据反馈数据优化 AI 回复质量</li>
        <li><strong>安全保护</strong>：检测异常访问、实施风险识别与危机干预</li>
        <li><strong>72小时随访</strong>：在高风险对话后，可能发送一封关怀邮件（可关闭）</li>
      </ol>
      <p><strong>我们绝不会：</strong></p>
      <ul style={{ marginLeft: 20 }}>
        <li>将你的对话内容、情绪记录或画像数据出售给任何第三方</li>
        <li>将你的数据用于商业广告定向推送</li>
        <li>在未经你明确同意的情况下，向他人披露你的具体对话内容</li>
      </ul>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>四、数据存储与安全</h2>
      <ul style={{ marginLeft: 20 }}>
        <li><strong>存储位置</strong>：腾讯云服务器（中国大陆），受《网络安全法》保护</li>
        <li><strong>传输加密</strong>：全站 HTTPS（Let's Encrypt 证书）</li>
        <li><strong>密码保护</strong>：bcrypt + salt（成本因子12），不可逆加密存储</li>
        <li><strong>敏感字段</strong>：日志中自动脱敏，不记录明文对话内容至系统日志</li>
        <li><strong>Cookie 安全</strong>：HttpOnly + Secure + SameSite=Lax，防止 XSS 盗取</li>
      </ul>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>五、你的数据权利</h2>
      <p>你对自己的数据拥有完整控制权：</p>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 20 }}>
        <thead>
          <tr style={{ background: '#f5f5f5', borderBottom: '2px solid #ddd' }}>
            <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>权利</th>
            <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>操作方式</th>
          </tr>
        </thead>
        <tbody>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}><strong>查看数据</strong></td>
            <td style={{ padding: 12 }}>登录后在个人中心查看对话历史、情绪记录、画像</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}><strong>删除对话历史</strong></td>
            <td style={{ padding: 12 }}>聊天页点击"清空聊天记录"</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}><strong>删除情绪记录</strong></td>
            <td style={{ padding: 12 }}>调用 DELETE /api/emotion/records 接口</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}><strong>重置用户画像</strong></td>
            <td style={{ padding: 12 }}>画像页点击"重置画像"</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}><strong>注销账号</strong></td>
            <td style={{ padding: 12 }}>联系 aini1187774151@gmail.com，我们将在 7 个工作日内处理</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}><strong>关闭随访通知</strong></td>
            <td style={{ padding: 12 }}>账号设置中关闭，或联系我们</td>
          </tr>
        </tbody>
      </table>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>六、用户画像与深度画像的特殊说明</h2>
      <p>用户画像和深度画像是系统对你情绪模式的<strong>辅助性推测</strong>，不是心理学评估结论，更不构成任何形式的医学诊断。</p>
      <p>深度画像的所有描述均使用推测性语言（"可能""也许""倾向于"），仅用于帮助 AI 更自然地回应你，不会作为你心理健康状况的官方记录。</p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>七、未成年人保护</h2>
      <p>本产品面向 18 岁以上大学生用户。如我们发现未成年用户使用本产品，将在合理期限内删除其相关数据。</p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>八、政策更新</h2>
      <p>本政策如有重大变更，将通过应用内通知或邮件提前告知。继续使用本产品视为接受更新后的政策。</p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>九、联系我们</h2>
      <ul style={{ marginLeft: 20 }}>
        <li>邮件：aini1187774151@gmail.com</li>
        <li>GitHub Issues：<a href="https://github.com/ky0404/yuanxinyeyu/issues" target="_blank" rel="noopener noreferrer" style={{ color: '#6366f1', textDecoration: 'none' }}>https://github.com/ky0404/yuanxinyeyu/issues</a></li>
        <li>线上体验：<a href="https://dukkha.top" target="_blank" rel="noopener noreferrer" style={{ color: '#6366f1', textDecoration: 'none' }}>https://dukkha.top</a></li>
      </ul>

      <p style={{ marginTop: 40, fontSize: 12, color: '#999', fontStyle: 'italic' }}>本隐私政策适用于 dukkha.top 及其 API 服务。</p>

      <hr style={{ margin: '40px 0', borderTop: '1px solid #eee' }} />
      <div style={{ textAlign: 'center', fontSize: 12, color: '#888' }}>
        
        <a href="/" style={{ color: '#6366f1', textDecoration: 'none' }}>返回首页</a>
      </div>
    </div>
  );
}

function TermsPage() {
  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '40px 24px', lineHeight: 1.8, background: '#fff', minHeight: '100vh', fontSize: 14, color: '#333' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 24 }}>媛心烨语 · 用户协议</h1>
      
      <div style={{ marginBottom: 32, color: '#666' }}>
        <p><strong>生效日期：</strong>2025年1月1日</p>
        <p><strong>适用版本：</strong>媛心烨语 v3.x</p>
      </div>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>一、接受条款</h2>
      <p>访问或使用媛心烨语（dukkha.top）即表示你同意遵守本用户协议。若不同意，请停止使用本产品。</p>
      <p>本产品由参赛团队开发，用于第十九届中国大学生计算机设计大赛，属于学术研究与实验性产品，非商业运营。</p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>二、服务说明</h2>
      
      <h3 style={{ fontSize: 16, fontWeight: 600, marginTop: 20, marginBottom: 12 }}>2.1 本产品提供的服务</h3>
      <ul style={{ marginLeft: 20, marginBottom: 16 }}>
        <li>基于大语言模型的情绪分析与陪伴对话</li>
        <li>个人情绪趋势追踪与可视化</li>
        <li>用户画像辅助（推测性，非诊断性）</li>
        <li>心理资源引导（热线推荐、专业机构建议）</li>
      </ul>

      <h3 style={{ fontSize: 16, fontWeight: 600, marginTop: 20, marginBottom: 12 }}>2.2 本产品不提供的服务</h3>
      <p><strong style={{ color: '#ef4444' }}>重要声明：媛心烨语不是医疗机构，不提供以下服务：</strong></p>
      <ul style={{ marginLeft: 20, marginBottom: 16 }}>
        <li>心理疾病诊断或治疗</li>
        <li>专业心理咨询（请联系持证心理咨询师）</li>
        <li>精神科用药建议</li>
        <li>危机处置替代服务</li>
      </ul>
      <p>AI 生成的回复基于统计模式，可能存在不准确、不适当或滞后的情况。<strong>请不要将 AI 回复作为心理健康状况的唯一判断依据。</strong></p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>三、用户责任</h2>
      <p>使用本产品时，你承诺：</p>
      <ol style={{ marginLeft: 20, marginBottom: 16 }}>
        <li>提供真实、准确的账号注册信息</li>
        <li>妥善保管账号密码，不与他人共享</li>
        <li>不利用本产品从事违法或有害活动</li>
        <li>不尝试破解、攻击或干扰系统正常运行</li>
        <li>不通过脚本、爬虫等方式批量调用接口</li>
        <li>不发布虚假、误导性或有害内容</li>
      </ol>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>四、账号管理</h2>
      <ul style={{ marginLeft: 20, marginBottom: 16 }}>
        <li><strong>注册邮箱登录：</strong>密码至少 6 位，建议使用强密码</li>
        <li><strong>邮箱验证码登录：</strong>首次使用自动创建账号</li>
        <li><strong>GitHub 授权登录：</strong>仅授权基本信息，可随时撤销</li>
        <li><strong>游客模式：</strong>每日有一定免费使用额度，数据仅保存在本地</li>
      </ul>
      <p>账号如长期未使用（超过 12 个月），我们可能在提前通知后清理相关数据。</p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>五、知识产权</h2>
      <ul style={{ marginLeft: 20, marginBottom: 16 }}>
        <li>AI 生成的对话内容版权归媛心烨语团队所有</li>
        <li>你发送的对话内容版权归你本人所有</li>
        <li>你授权我们使用你的对话数据改进模型（匿名化处理，可撤回）</li>
      </ul>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>六、免责条款</h2>
      <p>在法律允许的最大范围内，我们不对以下情形承担责任：</p>
      <ol style={{ marginLeft: 20, marginBottom: 16 }}>
        <li>AI 回复内容的准确性或适当性</li>
        <li>因技术故障导致的数据丢失</li>
        <li>因用户行为导致的任何损失</li>
        <li>服务中断或不可用</li>
        <li>第三方链接（如 GitHub、华为云）的内容或服务</li>
      </ol>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>七、危机干预限制</h2>
      <p>本产品具备基础危机检测能力（关键词识别 + LLM 风险分级），会在检测到高风险对话时自动追加心理援助热线信息（400-161-9995）。</p>
      <p>但这一机制<strong>不能保证完整识别所有危机情况</strong>，也<strong>不能替代专业危机干预</strong>。如你或身边的人处于心理危机中，请立即联系专业机构：</p>
      <ul style={{ marginLeft: 20, marginBottom: 16 }}>
        <li>全国心理援助热线：400-161-9995</li>
        <li>北京心理危机研究与干预中心：010-82951332</li>
        <li>当地医院精神科或心理科</li>
      </ul>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>八、协议修改</h2>
      <p>本协议如有实质性变更，将通过应用内通知提前 7 天告知。继续使用本产品视为接受修改后的协议。</p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>九、适用法律</h2>
      <p>本协议受中华人民共和国法律管辖。如发生争议，双方友好协商解决；协商不成的，提交本产品运营方所在地有管辖权的人民法院处理。</p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>十、联系我们</h2>
      <ul style={{ marginLeft: 20 }}>
        <li>邮件：aini1187774151@gmail.com</li>
        <li>线上体验：<a href="https://dukkha.top" target="_blank" rel="noopener noreferrer" style={{ color: '#6366f1', textDecoration: 'none' }}>https://dukkha.top</a></li>
      </ul>

      <hr style={{ margin: '40px 0', borderTop: '1px solid #eee' }} />
      <div style={{ textAlign: 'center', fontSize: 12, color: '#888' }}>
        <a href="/" style={{ color: '#6366f1', textDecoration: 'none' }}>返回首页</a>
      </div>
    </div>
  );
}

function DisclaimerPage() {
  return (
    <div style={{ maxWidth: 860, margin: '0 auto', padding: '40px 24px', lineHeight: 1.8, background: '#fff', minHeight: '100vh', fontSize: 14, color: '#333' }}>
      <h1 style={{ fontSize: 28, fontWeight: 700, marginBottom: 24 }}>媛心烨语 · 免责声明</h1>
      
      <div style={{ marginBottom: 32, color: '#666' }}>
        <p><strong>发布日期：</strong>2025年4月</p>
      </div>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>一、产品性质声明</h2>
      <p>媛心烨语（YuanXinYeYu）是一款<strong>人工智能情绪陪伴系统</strong>，面向大学生群体提供情绪倾诉、趋势分析和心理资源引导服务。</p>
      <p><strong>本产品不是：</strong></p>
      <ul style={{ marginLeft: 20, marginBottom: 16 }}>
        <li>医疗器械或医疗软件</li>
        <li>心理咨询服务平台</li>
        <li>精神疾病诊断工具</li>
        <li>危机干预专业机构</li>
      </ul>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>二、AI 内容免责</h2>
      <p>本产品的所有回复内容由人工智能模型生成，具有以下固有局限性：</p>
      <ol style={{ marginLeft: 20, marginBottom: 16 }}>
        <li><strong>不保证准确性</strong>：AI 基于统计模式生成内容，可能存在事实错误或判断偏差</li>
        <li><strong>不保证适当性</strong>：AI 回复不能完全适配每位用户的具体情况</li>
        <li><strong>不保证完整性</strong>：AI 可能无法识别所有潜在风险或情绪信号</li>
        <li><strong>不构成建议</strong>：任何 AI 回复均不构成医学、法律、财务或专业心理建议</li>
      </ol>
      <p>用户应对自己的决定和行为负责，不应将 AI 回复作为唯一的行动依据。</p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>三、用户画像免责</h2>
      <p>本产品的用户画像（UserProfile）和深度画像（DeepProfile）功能，基于用户历史对话自动推测生成，具有以下特性：</p>
      <ul style={{ marginLeft: 20, marginBottom: 16 }}>
        <li>所有描述均为<strong>推测性语言</strong>，非确定性判断</li>
        <li>画像内容可能存在偏差，不代表用户的真实心理状况</li>
        <li>画像不构成任何形式的心理学评估或诊断结论</li>
        <li>画像数据仅用于优化 AI 对话体验，不作为任何正式记录</li>
      </ul>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>四、危机干预免责</h2>
      <p>本产品具备基础的危机风险识别功能（四级分类：低/中/高/紧急），并在高风险情况下自动推送心理援助热线信息。</p>
      <p>但请注意：</p>
      <ul style={{ marginLeft: 20, marginBottom: 16 }}>
        <li>本系统的风险识别基于关键词规则和 LLM 判断，准确率约 98%（非 100%）</li>
        <li>系统可能存在漏识别（假阴性）或误识别（假阳性）情况</li>
        <li><strong>本系统不能替代专业危机干预，不能保证对所有危机情况的完整响应</strong></li>
      </ul>
      <p>如果你正在经历心理危机，<strong>请立即联系专业机构</strong>：</p>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 
 20 }}>
        <thead>
          <tr style={{ background: '#f5f5f5', borderBottom: '2px solid #ddd' }}>
            <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>机构</th>
            <th style={{ padding: 12, textAlign: 'left', fontWeight: 600 }}>联系方式</th>
          </tr>
        </thead>
        <tbody>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}>全国心理援助热线</td>
            <td style={{ padding: 12 }}>400-161-9995（24小时）</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}>北京心理危机研究与干预中心</td>
            <td style={{ padding: 12 }}>010-82951332</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}>希望24热线</td>
            <td style={{ padding: 12 }}>400-161-9995</td>
          </tr>
          <tr style={{ borderBottom: '1px solid #eee' }}>
            <td style={{ padding: 12 }}>当地医院精神科/心理科</td>
            <td style={{ padding: 12 }}>—</td>
          </tr>
        </tbody>
      </table>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>五、72小时随访免责</h2>
      <p>本产品在检测到高风险对话后，可能在约 72 小时后发送关怀邮件。</p>
      <ul style={{ marginLeft: 20, marginBottom: 16 }}>
        <li>随访邮件为温馨提醒，不构成专业干预</li>
        <li>邮件发送依赖 SMTP 服务可用性，不保证 100% 送达</li>
        <li>随访功能为辅助性质，不能替代专业跟进服务</li>
        <li>用户可随时关闭随访功能</li>
      </ul>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>六、服务可用性免责</h2>
      <p>由于本产品部署于 2核2G 服务器，系统资源有限：</p>
      <ul style={{ marginLeft: 20, marginBottom: 16 }}>
        <li>不保证 7×24 小时不间断服务（目标可用性 99.9%，但不作承诺）</li>
        <li>高并发时可能出现响应延迟</li>
        <li>AI 接口依赖华为云第三方服务，其不可用时本产品可能降级运行</li>
      </ul>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>七、未成年人使用免责</h2>
      <p>本产品面向 18 岁以上大学生用户设计。未成年人如在监护人知情同意下使用，监护人应承担相应监护责任，本团队不对未成年人使用行为导致的后果承担责任。</p>

      <h2 style={{ fontSize: 18, fontWeight: 700, marginTop: 32, marginBottom: 16, borderBottom: '2px solid #6366f1', paddingBottom: 8 }}>八、参赛作品性质说明</h2>
      <p>本产品为第十九届中国大学生计算机设计大赛参赛作品，属于学术研究与技术探索性质，非商业运营产品。</p>
      <p>团队对产品持续改进，但不对任何依赖本产品服务的商业决策或个人决定负责。</p>

      <hr style={{ margin: '40px 0', borderTop: '1px solid #eee' }} />
      <div style={{ textAlign: 'center', fontSize: 12, color: '#888' }}>
        <p style={{ marginBottom: 12 }}>如对本免责声明有任何疑问，请联系 aini1187774151@gmail.com</p>
        <a href="/" style={{ color: '#6366f1', textDecoration: 'none' }}>返回首页</a>
      </div>
    </div>
  );
}


