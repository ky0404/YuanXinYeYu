import { useState, useRef, useEffect, useCallback } from 'react';
import { Modal, message, Tooltip } from 'antd';
import {
  SendOutlined,
  DeleteOutlined,
  LineChartOutlined,
  HeartOutlined,
  LikeOutlined,
  LoadingOutlined,
  BulbOutlined,
  UserOutlined,
  LogoutOutlined,
  LoginOutlined,
  EyeOutlined,
  EyeInvisibleOutlined,
} from '@ant-design/icons';
import axios from 'axios';
import type { CancelTokenSource } from 'axios';
import './App.css';

axios.defaults.baseURL = '/';
axios.defaults.timeout = 20000;
axios.defaults.withCredentials = true;

const MIN_LEN = 5;
const MAX_LEN = 500;
const CAPTCHA_STORAGE_KEY = 'dukkha_slide_verify_v1';
const CAPTCHA_STORAGE_TTL = 30 * 60 * 1000;
const CAPTCHA_MESSAGE_KEY = 'dukkha_slide_verify_msg';
const CAPTCHA_VERIFY_DEBOUNCE = 500;

type ReplyMode = 'smart' | 'praise' | 'comfort';
type HistoryItem = { role: 'user' | 'assistant'; content: string };
type AuthUser = { id: number; email: string; username: string };

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

const EMOTION_CONFIG: Record<string, {
  gradient: string;
  label: string;
  glow: string;
  tagColor: string;
}> = {
  happy: { gradient: 'linear-gradient(135deg,#fbbf24,#f59e0b)', label: '开心', glow: 'rgba(251,191,36,0.4)', tagColor: '#f59e0b' },
  sad: { gradient: 'linear-gradient(135deg,#60a5fa,#3b82f6)', label: '低落', glow: 'rgba(96,165,250,0.4)', tagColor: '#3b82f6' },
  anxious: { gradient: 'linear-gradient(135deg,#a78bfa,#8b5cf6)', label: '焦虑', glow: 'rgba(167,139,250,0.4)', tagColor: '#8b5cf6' },
  angry: { gradient: 'linear-gradient(135deg,#f87171,#ef4444)', label: '愤怒', glow: 'rgba(248,113,113,0.4)', tagColor: '#ef4444' },
  calm: { gradient: 'linear-gradient(135deg,#34d399,#10b981)', label: '平静', glow: 'rgba(52,211,153,0.4)', tagColor: '#10b981' },
  neutral: { gradient: 'linear-gradient(135deg,#9ca3af,#6b7280)', label: '中性', glow: 'rgba(156,163,175,0.4)', tagColor: '#6b7280' },
};

const MODES: Record<ReplyMode, { label: string; icon: React.ReactNode; prefix: string; desc: string }> = {
  smart: { label: '智能分析', icon: <LineChartOutlined />, prefix: '✨', desc: '更懂情绪，也更会接住你' },
  praise: { label: '暖心夸夸', icon: <LikeOutlined />, prefix: '🌈', desc: '放大你的闪光点和价值感' },
  comfort: { label: '温柔安慰', icon: <HeartOutlined />, prefix: '☁️', desc: '先陪着你，不急着给答案' },
};

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
      verified: true,
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

const mapEmotion = (cat: number, text: string): string => {
  if (cat === 1) return 'happy';
  if (cat === 2) {
    if (['焦虑', '紧张', '担心', '压力', '不安', '失眠'].some((word) => text.includes(word))) return 'anxious';
    if (['生气', '愤怒', '讨厌', '烦', '委屈', '火大'].some((word) => text.includes(word))) return 'angry';
    return 'sad';
  }
  if (cat === 4) return 'calm';
  return 'neutral';
};

const stripPrefix = (text: string) => text.replace(/^[✨🌈☁️]\s*/, '');

const SlideCaptcha = ({
  onVerify,
  resetTrigger,
  verified,
}: {
  onVerify: (value: boolean) => void;
  resetTrigger: boolean;
  verified: boolean;
}) => {
  const [pos, setPos] = useState(0);
  const [done, setDone] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  const verifyAtRef = useRef(0);

  useEffect(() => {
    const raf = window.requestAnimationFrame(() => {
      const max = ref.current ? Math.max(ref.current.clientWidth - 52, 0) : 0;
      if (verified) {
        setDone(true);
        setPos(max);
        return;
      }
      setDone(false);
      setPos(0);
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
    const max = rect.width - 52;
    const next = Math.max(0, Math.min(clientX - rect.left - 24, max));
    setPos(next);
    if (next >= max - 2) finishVerify();
  }, [done, finishVerify]);

  const resetIfNeeded = useCallback(() => {
    if (!done) setPos(0);
  }, [done]);

  const startDrag = () => {
    if (done) return;
    const onMove = (event: MouseEvent) => handleMove(event.clientX);
    const onUp = () => {
      window.removeEventListener('mousemove', onMove);
      window.removeEventListener('mouseup', onUp);
      resetIfNeeded();
    };
    window.addEventListener('mousemove', onMove);
    window.addEventListener('mouseup', onUp);
  };

  const startTouch = (event: React.TouchEvent) => {
    if (done) return;
    event.preventDefault();
    const onMove = (touchEvent: TouchEvent) => {
      if (touchEvent.touches[0]) handleMove(touchEvent.touches[0].clientX);
    };
    const onUp = () => {
      window.removeEventListener('touchmove', onMove);
      window.removeEventListener('touchend', onUp);
      resetIfNeeded();
    };
    window.addEventListener('touchmove', onMove, { passive: false });
    window.addEventListener('touchend', onUp);
  };

  return (
    <div className="captcha-wrap" ref={ref}>
      <div
        className="captcha-progress"
        style={{
          width: pos + 52,
          background: done
            ? 'linear-gradient(90deg,#10b981,#34d399)'
            : 'linear-gradient(90deg,rgba(99,102,241,0.15),rgba(99,102,241,0.3))',
        }}
      />
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
const EmotionBall = ({ emotion = 'neutral', intensity = 5 }: { emotion?: string; intensity?: number }) => {
  const config = EMOTION_CONFIG[emotion] || EMOTION_CONFIG.neutral;
  const size = 58 + (intensity ?? 5) * 3;
  return (
    <div
      className="emotion-ball"
      style={{
        width: size,
        height: size,
        background: config.gradient,
        boxShadow: `0 4px 20px ${config.glow}`,
      }}
    >
      <span className="emotion-ball-label">{config.label}</span>
    </div>
  );
};

const EmotionTrend = ({ messages }: { messages: Message[] }) => {
  const wrapRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(320);
  const [animated, setAnimated] = useState(false);

  useEffect(() => {
    const update = () => {
      if (wrapRef.current) setWidth(Math.max(200, wrapRef.current.clientWidth - 40));
    };
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);

  useEffect(() => {
    setAnimated(false);
    const timer = window.setTimeout(() => setAnimated(true), 80);
    return () => window.clearTimeout(timer);
  }, [messages.length]);

  const data = messages
    .filter((item) => item.isUser && item.intensity)
    .map((item, index) => ({ x: index + 1, y: item.intensity ?? 5 }));

  if (data.length < 2) {
    return (
      <div className="trend-empty">
        <span className="trend-empty-icon">📈</span>
        多聊几句之后，这里会展示你的情绪变化趋势
      </div>
    );
  }

  const height = 120;
  const points = data.map((item, index) => ({
    x: (index / (data.length - 1)) * width + 20,
    y: height - 10 - (item.y / 10) * (height - 20),
    item,
  }));

  return (
    <div ref={wrapRef} style={{ width: '100%', height: 150, position: 'relative', paddingLeft: 24 }}>
      <div style={{ position: 'absolute', left: 24, top: 0, bottom: 24, width: 1, background: '#e2e8f0' }} />
      <div style={{ position: 'absolute', left: 24, right: 0, bottom: 24, height: 1, background: '#e2e8f0' }} />
      <div style={{ position: 'absolute', left: 24, right: 0, top: height / 2 - 12, height: 1, borderTop: '1px dashed #e2e8f0' }} />
      <svg width={width + 20} height={height} style={{ position: 'absolute', left: 0, top: 0 }}>
        <defs>
          <linearGradient id="trendLineGradient" x1="0%" y1="0%" x2="100%" y2="0%">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.7" />
            <stop offset="100%" stopColor="#ec4899" stopOpacity="1" />
          </linearGradient>
          <linearGradient id="trendFillGradient" x1="0%" y1="0%" x2="0%" y2="100%">
            <stop offset="0%" stopColor="#6366f1" stopOpacity="0.12" />
            <stop offset="100%" stopColor="#6366f1" stopOpacity="0" />
          </linearGradient>
        </defs>
        <polygon
          points={[
            ...points.map((point) => `${point.x},${point.y}`),
            `${points[points.length - 1].x},${height}`,
            `${points[0].x},${height}`,
          ].join(' ')}
          fill="url(#trendFillGradient)"
        />
        <polyline
          points={points.map((point) => `${point.x},${point.y}`).join(' ')}
          fill="none"
          stroke="url(#trendLineGradient)"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={animated ? 'trend-line' : ''}
          style={{ filter: 'drop-shadow(0 2px 6px rgba(99,102,241,0.3))' }}
        />
        {points.map((point, index) => (
          <Tooltip key={index} title={`第 ${point.item.x} 条消息 · 强度 ${point.item.y}/10`}>
            <circle cx={point.x} cy={point.y} r="5" fill="#fff" stroke="#6366f1" strokeWidth="2.5" className="trend-point" />
          </Tooltip>
        ))}
      </svg>
      <span style={{ position: 'absolute', left: 2, top: 2, fontSize: 10, color: '#94a3b8' }}>10</span>
      <span style={{ position: 'absolute', left: 2, top: height / 2 - 18, fontSize: 10, color: '#94a3b8' }}>5</span>
      <span style={{ position: 'absolute', left: 2, bottom: 20, fontSize: 10, color: '#94a3b8' }}>0</span>
      <span style={{ position: 'absolute', bottom: 2, left: 24, right: 0, textAlign: 'center', fontSize: 11, color: '#94a3b8' }}>
        情绪强度变化趋势（共 {data.length} 条记录）
      </span>
    </div>
  );
};

const AnalysisCard = ({ data, originalText }: { data: AnalysisPayload | null; originalText?: string }) => {
  if (!data) return null;
  const emotion = mapEmotion(data.sentiment_category, originalText || '');
  const config = EMOTION_CONFIG[emotion] || EMOTION_CONFIG.neutral;
  const categoryMap: Record<number, string> = { 1: '正向', 2: '负向', 3: '复杂混合', 4: '中性', 5: '不相关' };

  return (
    <div className="glass-card analysis-card" style={{ borderLeftColor: config.tagColor }}>
      <div className="analysis-header">
        <div className="analysis-info">
          <div className="analysis-title">📋 情绪分析结果</div>
          <div className="analysis-tags">
            <span className="emotion-tag" style={{ background: config.gradient, boxShadow: `0 2px 8px ${config.glow}` }}>
              {categoryMap[data.sentiment_category] ?? '未知'}
            </span>
            <span className="score-text">强度 {Number(data.sentiment_score || 0).toFixed(1)}/10</span>
          </div>
          {Array.isArray(data.keywords) && data.keywords.length > 0 && (
            <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
              {data.keywords.map((keyword, index) => (
                <span key={index} className="keyword-tag">{keyword}</span>
              ))}
            </div>
          )}
        </div>
        <EmotionBall emotion={emotion} intensity={data.sentiment_score} />
      </div>
      {data.guide && (
        <>
          <div className="analysis-divider" />
          <div className="guide-row">
            <BulbOutlined className="guide-icon" style={{ color: '#f59e0b' }} />
            <span className="guide-text">{data.guide}</span>
          </div>
        </>
      )}
    </div>
  );
};

const AuthModal = ({
  visible,
  onClose,
  onSuccess,
}: {
  visible: boolean;
  onClose: () => void;
  onSuccess: (user: AuthUser) => void;
}) => {
  const [tab, setTab] = useState<'login' | 'register'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [username, setUsername] = useState('');
  const [showPwd, setShowPwd] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!visible) setShowPwd(false);
  }, [visible]);

  const switchTab = (nextTab: 'login' | 'register') => {
    setTab(nextTab);
    setEmail('');
    setPassword('');
    setUsername('');
    setShowPwd(false);
  };

  const handleSubmit = async () => {
    if (!email.trim() || !password.trim()) {
      message.warning('邮箱和密码不能为空');
      return;
    }
    if (tab === 'register' && password.length < 6) {
      message.warning('密码至少 6 位');
      return;
    }

    setSubmitting(true);
    try {
      const url = tab === 'login' ? '/api/auth/login' : '/api/auth/register';
      const payload = tab === 'login'
        ? { email: email.trim(), password }
        : { email: email.trim(), password, username: username.trim() || undefined };
      const response = await axios.post(url, payload);
      if (response.data.code !== 200) throw new Error(response.data.msg || '操作失败');
      const user: AuthUser = response.data.data;
      message.success(tab === 'login' ? `欢迎回来，${user.username} 🎉` : `注册成功，欢迎你 ${user.username} 🎉`, 2);
      onSuccess(user);
    } catch (error: any) {
      message.error(error.response?.data?.msg || error.message || '网络错误，请稍后重试');
    } finally {
      setSubmitting(false);
    }
  };

  const handleKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter') handleSubmit();
  };

  if (!visible) return null;

  return (
    <div className="auth-overlay" onClick={onClose}>
      <div className="auth-modal glass-card" onClick={(event) => event.stopPropagation()}>
        <div className="top-bar" />
        <div className="auth-title"><span style={{ fontSize: 24 }}>💞</span>{tab === 'login' ? '欢迎回来' : '创建账号'}</div>
        <div className="auth-subtitle">{tab === 'login' ? '登录后自动同步你的对话和情绪记录' : '注册后即可永久保存你的聊天历史'}</div>
        <div className="auth-tabs">
          <button className={`auth-tab${tab === 'login' ? ' active' : ''}`} onClick={() => switchTab('login')}>登录</button>
          <button className={`auth-tab${tab === 'register' ? ' active' : ''}`} onClick={() => switchTab('register')}>注册</button>
        </div>
        <div className="auth-form">
          {tab === 'register' && (
            <div className="auth-field">
              <label className="auth-label">昵称（可选）</label>
              <input className="auth-input" type="text" placeholder="怎么称呼你？" value={username} onChange={(event) => setUsername(event.target.value)} onKeyDown={handleKeyDown} maxLength={50} />
            </div>
          )}
          <div className="auth-field">
            <label className="auth-label">邮箱</label>
            <input className="auth-input" type="email" placeholder="your@email.com" value={email} onChange={(event) => setEmail(event.target.value)} onKeyDown={handleKeyDown} />
          </div>
          <div className="auth-field">
            <label className="auth-label">密码{tab === 'register' ? '（至少 6 位）' : ''}</label>
            <div className="auth-pwd-wrap">
              <input className="auth-input" type={showPwd ? 'text' : 'password'} placeholder="••••••••" value={password} onChange={(event) => setPassword(event.target.value)} onKeyDown={handleKeyDown} />
              <button className="pwd-toggle" onClick={() => setShowPwd((prev) => !prev)} type="button">{showPwd ? <EyeInvisibleOutlined /> : <EyeOutlined />}</button>
            </div>
          </div>
          <button className="auth-submit-btn" onClick={handleSubmit} disabled={submitting}>
            {submitting ? <><LoadingOutlined />&nbsp;处理中...</> : tab === 'login' ? <><LoginOutlined />&nbsp;登录</> : <><UserOutlined />&nbsp;注册</>}
          </button>
          <div className="auth-switch">
            {tab === 'login' ? <>还没有账号？<span className="auth-link" onClick={() => switchTab('register')}>立即注册</span></> : <>已有账号？<span className="auth-link" onClick={() => switchTab('login')}>直接登录</span></>}
          </div>
        </div>
      </div>
    </div>
  );
};
export default function App() {
  const [authUser, setAuthUser] = useState<AuthUser | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [showAuth, setShowAuth] = useState(false);
  const [messages, setMessages] = useState<Message[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [verified, setVerified] = useState(false);
  const [resetCap, setResetCap] = useState(false);
  const [mode, setMode] = useState<ReplyMode>('smart');
  const [analysis, setAnalysis] = useState<AnalysisPayload | null>(null);

  const bottomRef = useRef<HTMLDivElement>(null);
  const cancelRef = useRef<CancelTokenSource | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

  const handleCaptchaVerify = useCallback((value: boolean) => {
    setVerified(value);
    if (value) {
      persistCaptchaState();
    } else {
      clearCaptchaState();
    }
  }, []);

  useEffect(() => {
    setVerified(readCaptchaState());
  }, []);

  useEffect(() => {
    if (!verified) return;
    const timer = window.setInterval(() => {
      if (!readCaptchaState()) {
        setVerified(false);
        setResetCap((prev) => !prev);
        showCaptchaMessage('info', '滑块验证已过期，请重新验证', 2);
      }
    }, 15000);
    return () => window.clearInterval(timer);
  }, [verified]);

  useEffect(() => {
    (async () => {
      try {
        const response = await axios.get('/api/auth/me');
        if (response.data.code === 200) setAuthUser(response.data.data);
      } catch {
        // ignore
      } finally {
        setAuthLoading(false);
      }
    })();
  }, []);

  useEffect(() => {
    if (!authUser) return;
    (async () => {
      try {
        const response = await axios.get('/api/history');
        if (response.data.code === 200 && Array.isArray(response.data.data.messages)) {
          const serverMessages: Message[] = response.data.data.messages;
          if (serverMessages.length > 0) {
            setMessages(serverMessages);
            setMode(response.data.data.mode || 'smart');
            message.info(`已恢复 ${serverMessages.length} 条历史记录 📚`, 2);
          }
        }
      } catch {
        try {
          const local = localStorage.getItem(`dukkha_${authUser.id}`);
          if (local) {
            const parsed = JSON.parse(local);
            if (Array.isArray(parsed)) setMessages(parsed);
          }
        } catch {}
      }
    })();
  }, [authUser]);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: 'smooth' });
    if (messages.length === 0) return;

    const cacheKey = authUser ? `dukkha_${authUser.id}` : 'dukkha_guest';
    try {
      localStorage.setItem(cacheKey, JSON.stringify(messages.slice(-60)));
    } catch {}

    if (!authUser) return;
    const timer = window.setTimeout(async () => {
      try {
        await axios.post('/api/history', { messages: messages.slice(-60), mode });
      } catch {}
    }, 800);
    return () => window.clearTimeout(timer);
  }, [messages, authUser, mode]);

  useEffect(() => {
    const textarea = textareaRef.current;
    if (!textarea) return;
    textarea.style.height = 'auto';
    textarea.style.height = `${Math.min(textarea.scrollHeight, 160)}px`;
  }, [input]);

  useEffect(() => () => {
    cancelRef.current?.cancel('unmount');
  }, []);

  const buildHistory = (): HistoryItem[] =>
    messages.slice(-6).map((item) => ({
      role: item.isUser ? 'user' : 'assistant',
      content: item.isUser ? item.text : stripPrefix(item.text),
    }));

  const handleLogout = async () => {
    Modal.confirm({
      title: '确认退出登录？',
      content: '退出后云端记录仍会保留，下次登录会自动恢复。',
      okText: '退出',
      cancelText: '取消',
      okButtonProps: { danger: true },
      onOk: async () => {
        await axios.post('/api/auth/logout').catch(() => {});
        setAuthUser(null);
        setMessages([]);
        setAnalysis(null);
        message.success('已退出登录', 2);
      },
    });
  };

  const sendMessage = async () => {
    if (loading) return;
    const text = input.trim();
    if (text.length < MIN_LEN) {
      message.warning(`至少输入 ${MIN_LEN} 个字哦～`, 2);
      return;
    }
    if (!verified) {
      showCaptchaMessage('warning', '请先完成滑块验证哦～', 2);
      return;
    }

    cancelRef.current?.cancel('duplicate');
    cancelRef.current = axios.CancelToken.source();

    const now = new Date().toLocaleTimeString('zh-CN', {
      hour: '2-digit',
      minute: '2-digit',
      hour12: false,
    });

    const userMessage: Message = {
      id: Date.now(),
      text,
      isUser: true,
      time: now,
      emotion: 'neutral',
      intensity: 5,
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
    setLoading(true);

    try {
      const response = await axios.post(
        '/api/emo_analysis',
        { text, mode, history: buildHistory() },
        { cancelToken: cancelRef.current.token },
      );
      const result = response.data;
      if (result.code !== 200) throw new Error(result.msg || '分析失败');

      const data = result.data || {};
      setAnalysis({ ...data, originalText: text });

      const emotion = mapEmotion(data.sentiment_category, text);
      const intensity = Math.min(10, Math.max(1, Math.round(data.sentiment_score || 5)));
      const aiText = data.reply ? `${MODES[mode].prefix} ${data.reply}` : `${MODES[mode].prefix} 我在这里，慢慢说。`;

      const aiMessage: Message = {
        id: Date.now() + 1,
        text: aiText,
        guide: data.guide,
        keywords: data.keywords || [],
        isUser: false,
        time: now,
        emotion,
        intensity,
        sentimentLabel: data.sentiment_label,
        mode,
      };

      setMessages((prev) => {
        const updated = prev.map((item) => item.id === userMessage.id ? { ...item, emotion, intensity } : item);
        return [...updated, aiMessage];
      });
    } catch (error: any) {
      if (axios.isCancel(error)) return;
      message.error(error.response?.data?.msg || error.message || '请稍后再试', 3);
      setMessages((prev) => {
        const updated = prev.map((item) => item.id === userMessage.id ? { ...item, emotion: 'neutral', intensity: 5 } : item);
        return [
          ...updated,
          {
            id: Date.now() + 1,
            text: `${MODES[mode].prefix} 我听见你了，虽然这次没有顺利分析，但我还在这里陪着你。`,
            isUser: false,
            time: now,
            emotion: 'neutral',
            intensity: 5,
          },
        ];
      });
    } finally {
      setLoading(false);
      cancelRef.current = null;
    }
  };

  const handleTextareaKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === 'Enter' && !event.shiftKey) {
      event.preventDefault();
      sendMessage();
    }
  };

  const clearAll = () => {
    Modal.confirm({
      title: '确认清空聊天记录？',
      content: authUser ? '本地和云端记录都会一起删除，操作后不可恢复。' : '本地聊天记录会被清空。',
      okText: '确认清空',
      cancelText: '再想想',
      okButtonProps: { danger: true },
      onOk: async () => {
        if (authUser) await axios.delete('/api/history').catch(() => {});
        const cacheKey = authUser ? `dukkha_${authUser.id}` : 'dukkha_guest';
        localStorage.removeItem(cacheKey);
        setMessages([]);
        setAnalysis(null);
        message.success('聊天记录已清空 ✨', 2);
      },
    });
  };

  const canSend = !loading && verified && input.trim().length >= MIN_LEN;

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

  return (
    <>
      <div className="page-bg" />
      <div className="bg-blob bg-blob-1" />
      <div className="bg-blob bg-blob-2" />
      <div className="bg-blob bg-blob-3" />

      <AuthModal
        visible={showAuth}
        onClose={() => setShowAuth(false)}
        onSuccess={(user) => {
          setAuthUser(user);
          setShowAuth(false);
        }}
      />

      <div className="app-layout">
        <div className="app-content">
          <div className="glass-card header-card">
            <div className="top-bar" />
            <div className="user-bar">
              {authUser ? (
                <div className="user-info">
                  <div className="user-avatar">{(authUser.username || authUser.email)[0].toUpperCase()}</div>
                  <span className="user-name">{authUser.username || authUser.email}</span>
                  <Tooltip title="退出登录">
                    <button className="logout-btn" onClick={handleLogout} type="button">
                      <LogoutOutlined />
                    </button>
                  </Tooltip>
                </div>
              ) : (
                <button className="login-btn" onClick={() => setShowAuth(true)} type="button">
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
              {(Object.entries(MODES) as Array<[ReplyMode, typeof MODES[ReplyMode]]>).map(([key, item]) => (
                <Tooltip key={key} title={item.desc} placement="bottom">
                  <button className={`mode-btn${mode === key ? ' active' : ''}`} onClick={() => setMode(key)} type="button">
                    {item.icon}&nbsp;{item.label}
                  </button>
                </Tooltip>
              ))}
            </div>
            <div className="mode-desc">{MODES[mode].desc}</div>

            {!authUser && (
              <div className="guest-banner">
                <span>游客聊天会先保存在本地。</span>
                <span className="guest-login-link" onClick={() => setShowAuth(true)}>登录后永久云端保存</span>
              </div>
            )}
          </div>

          <AnalysisCard data={analysis} originalText={analysis?.originalText} />

          <div className="glass-card chat-card">
            <div className="chat-body">
              {messages.length === 0 ? (
                <div className="empty-state">
                  <span className="empty-icon">🫶</span>
                  <span className="empty-text">
                    {authUser ? `${authUser.username}，今天心情怎么样？` : '还没有聊天记录，说说今天的心情吧～'}
                  </span>
                </div>
              ) : (
                <>
                  {messages.map((item) => {
                    const config = EMOTION_CONFIG[item.emotion || 'neutral'] || EMOTION_CONFIG.neutral;
                    return (
                      <div key={item.id} className={`message-wrap ${item.isUser ? 'user' : 'ai'}`}>
                        {item.isUser && item.emotion && item.emotion !== 'neutral' && (
                          <div className="bubble-tag">
                            <span className="emotion-tag" style={{ background: config.gradient, boxShadow: `0 2px 8px ${config.glow}`, fontSize: 11 }}>
                              {config.label}{item.intensity ? ` · ${item.intensity}/10` : ''}
                            </span>
                          </div>
                        )}
                        {!item.isUser && item.sentimentLabel && (
                          <div className="bubble-tag">
                            <span className="keyword-tag">{item.sentimentLabel}</span>
                          </div>
                        )}
                        <div className={`bubble ${item.isUser ? 'user' : 'ai'}`}>{item.text}</div>
                        {!item.isUser && item.keywords && item.keywords.length > 0 && (
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap', marginTop: 6 }}>
                            {item.keywords.map((keyword, index) => (
                              <span key={index} className="keyword-tag">{keyword}</span>
                            ))}
                          </div>
                        )}
                        <div className="bubble-time">{item.time}{item.mode && !item.isUser ? ` · ${MODES[item.mode]?.label}` : ''}</div>
                      </div>
                    );
                  })}
                  {loading && (
                    <div className="typing-bubble">
                      <div className="typing-dots">
                        <div className="typing-dot" />
                        <div className="typing-dot" />
                        <div className="typing-dot" />
                      </div>
                    </div>
                  )}
                  <div ref={bottomRef} />
                </>
              )}
            </div>
          </div>

          <div className="glass-card trend-card">
            <div className="trend-title">
              <LineChartOutlined /> 情绪趋势
            </div>
            <EmotionTrend messages={messages} />
          </div>

          <div className="glass-card input-card">
            <SlideCaptcha onVerify={handleCaptchaVerify} resetTrigger={resetCap} verified={verified} />
            <div className="sync-hint">
              {verified ? '滑块验证已缓存，本设备 30 分钟内可连续对话' : '完成一次滑块验证后，30 分钟内无需重复验证'}
            </div>

            <textarea
              ref={textareaRef}
              className="chat-textarea"
              value={input}
              onChange={(event) => setInput(event.target.value.slice(0, MAX_LEN))}
              onKeyDown={handleTextareaKeyDown}
              placeholder={`今天心情怎么样？（至少 ${MIN_LEN} 字，Shift+Enter 换行）`}
              disabled={loading}
              maxLength={MAX_LEN}
              rows={3}
            />

            <div className={`char-count${input.length > MAX_LEN * 0.9 ? ' warn' : ''}${input.length >= MAX_LEN ? ' over' : ''}`}>
              {input.length} / {MAX_LEN}
            </div>

            <button className="send-btn" onClick={sendMessage} disabled={!canSend} type="button">
              {loading ? <><LoadingOutlined style={{ fontSize: 18 }} />&nbsp;正在回应...</> : <><SendOutlined style={{ fontSize: 16 }} />&nbsp;发送消息</>}
            </button>

            <button className="clear-btn" onClick={clearAll} type="button">
              <DeleteOutlined />&nbsp;清空聊天记录
            </button>

            {authUser && messages.length > 0 && (
              <div className="sync-hint">☁️ 已自动同步到云端</div>
            )}
          </div>
        </div>
      </div>
    </>
  );
}
